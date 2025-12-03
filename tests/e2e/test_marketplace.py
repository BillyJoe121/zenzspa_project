from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import CartItem, Product, ProductVariant, ProductImage
from spa.models import ServiceCategory
from users.models import CustomUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client_user():
    return CustomUser.objects.create_user(
        phone_number="+573600000001",
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
    )


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def _make_product(name="Aceite Relax", price=Decimal("50000"), stock=5, vip_price=None):
    cat = ServiceCategory.objects.create(name=f"Cat {name}", description="desc")
    product = Product.objects.create(
        name=name,
        description="Aceite esencial",
        category=cat,
        is_active=True,
    )
    variant = ProductVariant.objects.create(
        product=product,
        name="Botella 50ml",
        sku=f"SKU-{name[:4]}",
        price=price,
        vip_price=vip_price,
        stock=stock,
    )
    # Imagen dummy (evitar validaciones de archivo real)
    ProductImage.objects.create(product=product, image="product_images/dummy.jpg", is_primary=True)
    return product, variant


def test_product_catalog_shows_active_only(api_client, client_user):
    active, _ = _make_product(name="Activo")
    inactive_cat = ServiceCategory.objects.create(name="Cat Inactivo", description="x")
    inactive = Product.objects.create(name="Inactivo", description="desc", category=inactive_cat, is_active=False)
    ProductVariant.objects.create(product=inactive, name="Var", sku="SKU-INAC", price=Decimal("10000"), stock=2)

    _auth(api_client, client_user)
    url = reverse("product-list")
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    names = [p["name"] for p in data]
    assert active.name in names
    assert inactive.name not in names


def test_product_detail_includes_variants_and_vip_price(api_client, client_user):
    product, variant = _make_product(vip_price=Decimal("40000"))

    _auth(api_client, client_user)
    url = reverse("product-detail", kwargs={"pk": product.id})
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    assert any(v["sku"] == variant.sku for v in resp.data["variants"])
    # vip_price visible para usuario autenticado
    assert Decimal(resp.data["variants"][0]["vip_price"]) == variant.vip_price


def test_add_to_cart_happy_path(api_client, client_user):
    product, variant = _make_product(stock=10)
    _auth(api_client, client_user)

    url = reverse("cart-add-item")
    resp = api_client.post(url, {"variant_id": str(variant.id), "quantity": 2}, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    cart = resp.data
    assert cart["items"][0]["quantity"] == 2
    assert str(cart["items"][0]["product"]["id"]) == str(product.id)


def test_add_to_cart_no_stock(api_client, client_user):
    _, variant = _make_product(stock=0)
    _auth(api_client, client_user)

    url = reverse("cart-add-item")
    resp = api_client.post(url, {"variant_id": str(variant.id), "quantity": 1}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "stock" in str(resp.data).lower()


def test_add_to_cart_exceeds_stock(api_client, client_user):
    _, variant = _make_product(stock=3)
    _auth(api_client, client_user)

    url = reverse("cart-add-item")
    resp = api_client.post(url, {"variant_id": str(variant.id), "quantity": 5}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "stock" in str(resp.data).lower()


def test_view_cart_and_totals(api_client, client_user):
    product, variant = _make_product(price=Decimal("20000"), stock=5)
    _auth(api_client, client_user)

    api_client.post(reverse("cart-add-item"), {"variant_id": str(variant.id), "quantity": 2}, format="json")
    resp = api_client.get(reverse("cart-my-cart"))

    assert resp.status_code == status.HTTP_200_OK
    total = Decimal(str(resp.data["total"]))
    assert total == Decimal("40000")
    assert resp.data["items"][0]["quantity"] == 2


def test_update_cart_item_quantity(api_client, client_user):
    _, variant = _make_product(stock=10)
    _auth(api_client, client_user)
    add_resp = api_client.post(reverse("cart-add-item"), {"variant_id": str(variant.id), "quantity": 1}, format="json")
    cart_item_id = add_resp.data["items"][0]["id"]

    url = f"/api/v1/marketplace/cart/{cart_item_id}/update-item/"
    update_resp = api_client.put(url, {"quantity": 3}, format="json")

    assert update_resp.status_code == status.HTTP_200_OK
    quantities = [item["quantity"] for item in update_resp.data["items"]]
    assert 3 in quantities


def test_remove_cart_item(api_client, client_user):
    _, variant = _make_product(stock=10)
    _auth(api_client, client_user)
    add_resp = api_client.post(reverse("cart-add-item"), {"variant_id": str(variant.id), "quantity": 1}, format="json")
    cart_item_id = add_resp.data["items"][0]["id"]

    url = f"/api/v1/marketplace/cart/{cart_item_id}/remove-item/"
    delete_resp = api_client.delete(url)
    assert delete_resp.status_code == status.HTTP_204_NO_CONTENT
    assert not CartItem.objects.filter(id=cart_item_id).exists()
