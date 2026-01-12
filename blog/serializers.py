from rest_framework import serializers
from .models import Article, Category, Tag, ArticleImage


class CategorySerializer(serializers.ModelSerializer):
    """Serializer para categorías"""
    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'articles_count', 'created_at', 'updated_at']
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def get_articles_count(self, obj):
        return obj.articles.filter(status='published').count()


class TagSerializer(serializers.ModelSerializer):
    """Serializer para etiquetas"""
    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'articles_count', 'created_at']
        read_only_fields = ['slug', 'created_at']

    def get_articles_count(self, obj):
        return obj.articles.filter(status='published').count()


class ArticleImageSerializer(serializers.ModelSerializer):
    """Serializer para imágenes de artículos"""
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ArticleImage
        fields = ['id', 'image', 'image_url', 'alt_text', 'caption', 'order', 'created_at']
        read_only_fields = ['created_at']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ArticleListSerializer(serializers.ModelSerializer):
    """Serializer para listado de artículos (vista resumida)"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    author_display = serializers.CharField(source='get_author_display', read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    is_published = serializers.BooleanField(read_only=True)

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'slug', 'subtitle', 'excerpt',
            'cover_image_url', 'cover_image_alt',
            'category_name', 'category_slug', 'tags',
            'author_display', 'status', 'is_published',
            'published_at', 'views_count', 'reading_time_minutes',
            'is_featured', 'created_at', 'updated_at'
        ]

    def get_cover_image_url(self, obj):
        return obj.cover_image if obj.cover_image else None


class ArticleDetailSerializer(serializers.ModelSerializer):
    """Serializer para detalle completo de artículo"""
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True,
        required=False,
        allow_null=True
    )
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='tags',
        write_only=True,
        many=True,
        required=False
    )
    author_display = serializers.CharField(source='get_author_display', read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    images = ArticleImageSerializer(many=True, read_only=True)
    is_published = serializers.BooleanField(read_only=True)

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'slug', 'subtitle', 'excerpt', 'content',
            'cover_image', 'cover_image_url', 'cover_image_alt',
            'category', 'category_id', 'tags', 'tag_ids',
            'author', 'author_display', 'author_name',
            'status', 'is_published', 'published_at',
            'meta_title', 'meta_description',
            'views_count', 'reading_time_minutes',
            'is_featured', 'featured_order',
            'images', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'slug', 'views_count', 'reading_time_minutes',
            'created_at', 'updated_at', 'is_published'
        ]

    def get_cover_image_url(self, obj):
        return obj.cover_image if obj.cover_image else None

    def update(self, instance, validated_data):
        # Manejar tags si se proporcionan
        tags = validated_data.pop('tags', None)

        # Actualizar el resto de campos
        instance = super().update(instance, validated_data)

        # Actualizar tags si se proporcionaron
        if tags is not None:
            instance.tags.set(tags)

        return instance


class ArticleCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/editar artículos (admin)"""
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source='tags',
        many=True,
        required=False
    )

    class Meta:
        model = Article
        fields = [
            'title', 'subtitle', 'excerpt', 'content',
            'cover_image', 'cover_image_alt',
            'category', 'tag_ids',
            'author_name', 'status', 'published_at',
            'meta_title', 'meta_description',
            'is_featured', 'featured_order'
        ]

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])

        # Asignar autor automáticamente
        if 'author' not in validated_data:
            validated_data['author'] = self.context['request'].user

        article = Article.objects.create(**validated_data)
        article.tags.set(tags)

        return article

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tags is not None:
            instance.tags.set(tags)

        return instance
