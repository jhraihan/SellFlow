from .manual import ManualAdapter
from .pathao import PathaoAdapter
from .steadfast import SteadfastAdapter

ADAPTERS = {
    ManualAdapter.code: ManualAdapter,
    PathaoAdapter.code: PathaoAdapter,
    SteadfastAdapter.code: SteadfastAdapter,
}


def get_adapter_class(adapter_key):
    return ADAPTERS.get(adapter_key)


def build_adapter(store_courier):
    adapter_class = get_adapter_class(store_courier.courier.adapter_key)
    if adapter_class is None:
        from .manual import ManualAdapter as Fallback

        return Fallback()
    return adapter_class(
        credentials=store_courier.credentials,
        config=store_courier.config,
    )


def available_adapters():
    return [
        {
            "code": cls.code,
            "display_name": cls.display_name,
            "supports_api": cls.supports_api,
            "supports_webhook": cls.supports_webhook,
            "supports_quote": cls.supports_quote,
            "supports_cancel": cls.supports_cancel,
        }
        for cls in ADAPTERS.values()
    ]
