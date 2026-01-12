from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ArticleViewSet, CategoryViewSet, TagViewSet, ArticleImageViewSet

# Router para los ViewSets
router = DefaultRouter()
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'images', ArticleImageViewSet, basename='article-image')

urlpatterns = [
    path('', include(router.urls)),
]
