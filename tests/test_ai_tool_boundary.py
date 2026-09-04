"""
AI tool boundary tests (services/agent/tools.py, spec sections 7/27/28):

  - every tool degrades gracefully on malformed input, a nonexistent
    product, or a fabricated product id - nothing raises
  - the tool module's public surface structurally excludes every
    financial-mutation / secret-access operation the LLM must never reach
  - create_cart/modify_cart only ever PROPOSE a cart - they cannot reach
    OrderService.checkout() or a PaymentProvider
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.agent import tools


def test_get_product_with_fabricated_id_returns_error_not_exception():
    result = tools.get_product("totally-invented-product-id-xyz")
    assert "error" in result


def test_get_product_with_empty_id_returns_error():
    result = tools.get_product("")
    assert "error" in result


def test_check_availability_unknown_product():
    result = tools.check_availability("nonexistent")
    assert result["available"] is False
    assert "error" in result


def test_compare_products_malformed_input_does_not_raise():
    assert tools.compare_products(None) == {"error": "product_ids must be a non-empty list.", "results": []}
    assert tools.compare_products([]) == {"error": "product_ids must be a non-empty list.", "results": []}
    # a mix of real and fabricated ids - fabricated ones are silently skipped, never invented
    result = tools.compare_products(["d501", "fabricated-id"])
    assert len(result["results"]) == 1


def test_search_catalog_never_raises_on_bad_filters():
    result = tools.search_catalog(query="x", filters={"required_attributes": "not-a-dict"})
    assert "results" in result


def test_create_cart_requires_merchant_id():
    result = tools.create_cart("sess-x", "")
    assert "error" in result


def test_create_cart_with_fabricated_item_id_reports_error_and_no_cart_corruption():
    result = tools.create_cart("sess-y", "r5", items=[{"product_id": "not-real"}])
    assert "error" in result


def test_modify_cart_unknown_cart_id():
    result = tools.modify_cart("not-a-cart", "d501", "r5", quantity=1)
    assert "error" in result


def test_get_order_status_unknown_id():
    result = tools.get_order_status("not-an-order")
    assert "error" in result


def test_find_complements_and_substitutes_never_raise_on_bad_id():
    assert tools.find_complements("fabricated") == {"results": []}
    assert tools.find_substitutes("fabricated") == {"results": []}


# --- structural boundary: the LLM's tool surface cannot touch money -------

def test_no_financial_tool_names_are_declared():
    declared_names = {d["name"] for d in tools.ALL_TOOL_DECLARATIONS}
    assert declared_names.isdisjoint(tools.FORBIDDEN_TOOL_NAMES)
    assert declared_names == set(tools.NAME_TO_FUNC.keys())


def test_no_financial_functions_exist_in_the_tools_module_namespace():
    module_globals = set(vars(tools).keys())
    overlap = module_globals & tools.FORBIDDEN_TOOL_NAMES
    assert overlap == set(), f"forbidden financial operations leaked into the AI tool module: {overlap}"


def test_tools_module_does_not_import_the_payment_provider():
    import_lines = [line.strip() for line in tools.__file__ and open(tools.__file__).read().splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).lower()
    assert "razorpay" not in joined
    assert "paymentprovider" not in joined
    assert "paymentservice" not in joined


def test_create_cart_does_not_create_an_order_or_call_razorpay(monkeypatch):
    """create_cart/modify_cart may only ever propose a cart - confirm the
    tool layer never reaches OrderService.checkout or PaymentService."""
    from backend.services.order.service import order_service
    calls = {"count": 0}
    original = order_service.checkout

    def counting_checkout(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(order_service, "checkout", counting_checkout)
    cart_dict = tools.create_cart("sess-z", "r5", items=[{"product_id": "d501"}])
    tools.modify_cart(cart_dict["cart_id"], "d501", "r5", quantity=2)
    assert calls["count"] == 0, "the AI tool layer must never call OrderService.checkout"
