import io
from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, StockItem
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products/"
CATEGORIES = "/api/v1/categories/"
STOCK = "/api/v1/stock/"


@pytest.fixture
def owner_store(make_user, make_store):
    owner = make_user(email="owner@example.com")
    return owner, make_store(owner)


class TestProductCreation:
    def test_creates_simple_product_with_stock(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {"name": "Cotton Kurti", "selling_price": "1200.00",
             "cost_price": "700.00", "opening_stock": 25},
            format="json",
        )

        assert response.status_code == 201
        product = Product.objects.get(id=response.data["id"])
        item = StockItem.objects.get(product=product, variant__isnull=True)
        assert item.on_hand == 25

    def test_sku_is_generated_when_blank(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS, {"name": "Cotton Kurti", "selling_price": "1200"},
            format="json",
        )

        assert response.data["sku"].startswith("COTTONKU")

    def test_duplicate_sku_rejected(self, owner_store, auth):
        owner, store = owner_store
        client = auth(owner, store=store)
        body = {"name": "Kurti", "selling_price": "100", "sku": "ABC-1"}

        assert client.post(PRODUCTS, body, format="json").status_code == 201
        second = client.post(
            PRODUCTS, {**body, "name": "Other"}, format="json"
        )
        assert second.status_code == 400

    def test_creates_product_with_variants(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {
                "name": "T-Shirt",
                "selling_price": "550.00",
                "has_variants": True,
                "variants": [
                    {"option1_name": "Size", "option1_value": "M"},
                    {"option1_name": "Size", "option1_value": "L",
                     "price_override": "600.00"},
                ],
            },
            format="json",
        )

        assert response.status_code == 201
        product = Product.objects.get(id=response.data["id"])
        assert product.variants.count() == 2
        assert StockItem.objects.filter(product=product).count() == 2

    def test_variant_price_override_applies(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {
                "name": "T-Shirt", "selling_price": "550.00",
                "has_variants": True,
                "variants": [
                    {"option1_name": "Size", "option1_value": "M"},
                    {"option1_name": "Size", "option1_value": "XL",
                     "price_override": "650.00"},
                ],
            },
            format="json",
        )

        prices = {
            v["option1_value"]: v["selling_price"]
            for v in response.data["variants"]
        }
        assert Decimal(prices["M"]) == Decimal("550.00")
        assert Decimal(prices["XL"]) == Decimal("650.00")

    def test_duplicate_variant_combination_rejected(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {
                "name": "T-Shirt", "selling_price": "550",
                "has_variants": True,
                "variants": [
                    {"option1_name": "Size", "option1_value": "M"},
                    {"option1_name": "Size", "option1_value": "M"},
                ],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_variants_require_has_variants_flag(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {
                "name": "T-Shirt", "selling_price": "550",
                "variants": [{"option1_name": "Size", "option1_value": "M"}],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_opening_stock_rejected_for_variant_product(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            PRODUCTS,
            {
                "name": "T-Shirt", "selling_price": "550",
                "has_variants": True, "opening_stock": 10,
                "variants": [{"option1_name": "Size", "option1_value": "M"}],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_delete_deactivates_rather_than_removes(self, owner_store, auth):
        owner, store = owner_store
        client = auth(owner, store=store)
        created = client.post(
            PRODUCTS, {"name": "Kurti", "selling_price": "100"}, format="json"
        )
        product_id = created.data["id"]

        assert client.delete(f"{PRODUCTS}{product_id}/").status_code == 204
        product = Product.objects.get(id=product_id)
        assert product.is_active is False


class TestCostPriceVisibility:
    def test_owner_sees_cost_and_margin(self, owner_store, auth):
        owner, store = owner_store
        client = auth(owner, store=store)
        created = client.post(
            PRODUCTS,
            {"name": "Kurti", "selling_price": "1200", "cost_price": "700"},
            format="json",
        )

        detail = client.get(f"{PRODUCTS}{created.data['id']}/")
        assert "cost_price" in detail.data
        assert Decimal(detail.data["margin"]) == Decimal("500.00")

    def test_order_staff_cannot_see_cost_or_margin(
        self, owner_store, make_user, make_member, auth
    ):
        owner, store = owner_store
        auth(owner, store=store).post(
            PRODUCTS,
            {"name": "Kurti", "selling_price": "1200", "cost_price": "700"},
            format="json",
        )

        staff = make_user(email="staff@example.com")
        make_member(store, staff, StoreRole.ORDER_STAFF)

        listing = auth(staff, store=store).get(PRODUCTS)
        assert listing.status_code == 200
        row = listing.data["results"][0]
        assert "cost_price" not in row

    def test_order_staff_cannot_create_products(
        self, owner_store, make_user, make_member, auth
    ):
        owner, store = owner_store
        staff = make_user(email="staff@example.com")
        make_member(store, staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=store).post(
            PRODUCTS, {"name": "Kurti", "selling_price": "100"}, format="json"
        )
        assert response.status_code == 403


class TestProductTenancy:
    def test_products_are_scoped_to_the_store(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        Product.objects.create(
            store=store_a, name="Alice Kurti", selling_price=Decimal("100")
        )
        Product.objects.create(
            store=store_b, name="Bob Cable", selling_price=Decimal("200")
        )

        response = auth(alice, store=store_a).get(PRODUCTS)
        names = {r["name"] for r in response.data["results"]}
        assert names == {"Alice Kurti"}

    def test_cannot_read_another_stores_product(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        foreign = Product.objects.create(
            store=store_b, name="Bob Cable", selling_price=Decimal("200")
        )

        response = auth(alice, store=store_a).get(f"{PRODUCTS}{foreign.id}/")
        assert response.status_code == 404

    def test_same_sku_allowed_in_different_stores(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        body = {"name": "Kurti", "selling_price": "100", "sku": "SHARED-1"}
        first = auth(alice, store=store_a).post(PRODUCTS, body, format="json")
        second = auth(bob, store=store_b).post(PRODUCTS, body, format="json")

        assert first.status_code == 201
        assert second.status_code == 201


class TestCategories:
    def test_create_and_list(self, owner_store, auth):
        owner, store = owner_store
        client = auth(owner, store=store)

        created = client.post(CATEGORIES, {"name": "Sarees"}, format="json")
        assert created.status_code == 201
        assert created.data["slug"] == "sarees"

        listing = client.get(CATEGORIES)
        assert len(listing.data) == 1

    def test_nesting_beyond_one_level_rejected(self, owner_store, auth):
        owner, store = owner_store
        client = auth(owner, store=store)

        top = client.post(CATEGORIES, {"name": "Clothing"}, format="json")
        mid = client.post(
            CATEGORIES, {"name": "Sarees", "parent": top.data["id"]},
            format="json",
        )
        assert mid.status_code == 201

        deep = client.post(
            CATEGORIES, {"name": "Silk", "parent": mid.data["id"]},
            format="json",
        )
        assert deep.status_code == 400

    def test_cannot_use_another_stores_category(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        foreign = Category.objects.create(store=store_b, name="Bob Cat")

        response = auth(alice, store=store_a).post(
            PRODUCTS,
            {"name": "Kurti", "selling_price": "100", "category": foreign.id},
            format="json",
        )
        assert response.status_code == 400


class TestStockEndpoints:
    def test_receive_stock_endpoint(self, owner_store, auth):
        owner, store = owner_store
        product = Product.objects.create(
            store=store, name="Kurti", selling_price=Decimal("100")
        )
        item = get_or_create_stock_item(product, None)

        response = auth(owner, store=store).post(
            "/api/v1/stock/receive/",
            {"stock_item": item.id, "quantity": 30, "reason": "Restock"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["stock"]["on_hand"] == 30

    def test_adjust_stock_endpoint(self, owner_store, auth):
        owner, store = owner_store
        product = Product.objects.create(
            store=store, name="Kurti", selling_price=Decimal("100")
        )
        item = get_or_create_stock_item(product, None)
        receive_stock(item, 50)

        response = auth(owner, store=store).post(
            "/api/v1/stock/adjust/",
            {"stock_item": item.id, "new_on_hand": 45, "reason": "Stock count"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["stock"]["on_hand"] == 45
        assert response.data["movement"]["quantity"] == -5

    def test_adjust_requires_reason(self, owner_store, auth):
        owner, store = owner_store
        product = Product.objects.create(
            store=store, name="Kurti", selling_price=Decimal("100")
        )
        item = get_or_create_stock_item(product, None)

        response = auth(owner, store=store).post(
            "/api/v1/stock/adjust/",
            {"stock_item": item.id, "new_on_hand": 5, "reason": ""},
            format="json",
        )
        assert response.status_code == 400

    def test_cannot_adjust_another_stores_stock(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        foreign_product = Product.objects.create(
            store=store_b, name="Bob Cable", selling_price=Decimal("200")
        )
        foreign_item = get_or_create_stock_item(foreign_product, None)

        response = auth(alice, store=store_a).post(
            "/api/v1/stock/adjust/",
            {"stock_item": foreign_item.id, "new_on_hand": 999,
             "reason": "Hijack"},
            format="json",
        )

        assert response.status_code == 400
        foreign_item.refresh_from_db()
        assert foreign_item.on_hand == 0

    def test_low_stock_filter(self, owner_store, auth):
        owner, store = owner_store
        low = Product.objects.create(
            store=store, name="Low", selling_price=Decimal("100"),
            low_stock_threshold=10,
        )
        high = Product.objects.create(
            store=store, name="High", selling_price=Decimal("100"),
            low_stock_threshold=5,
        )
        receive_stock(get_or_create_stock_item(low, None), 3)
        receive_stock(get_or_create_stock_item(high, None), 80)

        response = auth(owner, store=store).get(f"{STOCK}?low_stock=true")
        names = {r["product_name"] for r in response.data["results"]}
        assert names == {"Low"}

    def test_stock_summary(self, owner_store, auth):
        owner, store = owner_store
        product = Product.objects.create(
            store=store, name="Kurti", selling_price=Decimal("100")
        )
        receive_stock(get_or_create_stock_item(product, None), 40)

        response = auth(owner, store=store).get(f"{STOCK}summary/")
        assert response.data["on_hand"] == 40
        assert response.data["available"] == 40


class TestCsvImport:
    def _csv(self, rows):
        header = (
            "name,sku,category,selling_price,cost_price,opening_stock\n"
        )
        return io.BytesIO((header + rows).encode("utf-8"))

    def test_dry_run_does_not_create(self, owner_store, auth):
        owner, store = owner_store
        upload = self._csv("Kurti,,Clothing,1200,700,10\n")

        response = auth(owner, store=store).post(
            "/api/v1/products/import/",
            {"file": upload, "commit": "false"},
            format="multipart",
        )

        assert response.status_code == 200
        assert response.data["dry_run"] is True
        assert response.data["valid_count"] == 1
        assert response.data["committed"] is False
        assert Product.objects.filter(store=store).count() == 0

    def test_commit_creates_products_and_stock(self, owner_store, auth):
        owner, store = owner_store
        upload = self._csv("Kurti,,Clothing,1200,700,10\nSaree,,Clothing,2500,1500,4\n")

        response = auth(owner, store=store).post(
            "/api/v1/products/import/",
            {"file": upload, "commit": "true"},
            format="multipart",
        )

        assert response.status_code == 200
        assert response.data["committed"] is True
        assert response.data["created_count"] == 2
        assert Product.objects.filter(store=store).count() == 2

        kurti = Product.objects.get(store=store, name="Kurti")
        item = StockItem.objects.get(product=kurti)
        assert item.on_hand == 10

    def test_invalid_rows_block_the_commit(self, owner_store, auth):
        owner, store = owner_store
        upload = self._csv("Kurti,,Clothing,1200,700,10\n,,Clothing,500,200,2\n")

        response = auth(owner, store=store).post(
            "/api/v1/products/import/",
            {"file": upload, "commit": "true"},
            format="multipart",
        )

        assert response.data["error_count"] == 1
        assert response.data["committed"] is False
        assert Product.objects.filter(store=store).count() == 0

    def test_duplicate_sku_within_file_reported(self, owner_store, auth):
        owner, store = owner_store
        upload = self._csv(
            "Kurti,DUP-1,Clothing,100,50,1\nSaree,DUP-1,Clothing,200,80,1\n"
        )

        response = auth(owner, store=store).post(
            "/api/v1/products/import/",
            {"file": upload, "commit": "false"},
            format="multipart",
        )

        assert response.data["error_count"] == 1
        assert "Duplicate SKU" in response.data["errors"][0]["message"]

    def test_export_returns_csv(self, owner_store, auth):
        owner, store = owner_store
        Product.objects.create(
            store=store, name="Kurti", selling_price=Decimal("1200")
        )

        response = auth(owner, store=store).get("/api/v1/products/export/")

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        body = response.content.decode()
        assert "Kurti" in body
