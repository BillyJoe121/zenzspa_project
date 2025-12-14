"""
Management command para asociar imágenes de productos de forma interactiva.
Uso: python manage.py link_product_images
"""
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files import File
from marketplace.models import Product, ProductImage


class Command(BaseCommand):
    help = "Asocia imágenes de productos de forma interactiva o automática"

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Asocia automáticamente las imágenes según la carpeta'
        )

    def handle(self, *args, **options):
        media_root = Path("media/products")

        if not media_root.exists():
            self.stdout.write(self.style.ERROR("La carpeta media/products no existe"))
            return

        # Mapeo de carpetas a nombres de productos
        FOLDER_TO_PRODUCT = {
            "aceites-esenciales": "Aceites Esenciales Puros",
            "velas": "Velas Aromáticas de Soja",
            "brumas": "Bruma de Almohada Deep Sleep",
            "aceites-masaje": "Aceite de Masaje Profesional",
            "sales": "Sales de Baño Detox",
            "joyeria": ["Pulsera Tejida Protección", "Pulsera Tejida Amor Propio", "Pulsera Tejida Balance"],
        }

        auto_mode = options['auto']

        for folder_name, product_names in FOLDER_TO_PRODUCT.items():
            folder_path = media_root / folder_name

            if not folder_path.exists():
                continue

            # Buscar imágenes en la carpeta
            image_files = list(folder_path.glob("*.jpg")) + \
                         list(folder_path.glob("*.jpeg")) + \
                         list(folder_path.glob("*.png")) + \
                         list(folder_path.glob("*.webp"))

            if not image_files:
                continue

            # Si product_names es una lista, significa múltiples productos
            if isinstance(product_names, list):
                products = Product.objects.filter(name__in=product_names, is_active=True)
            else:
                products = Product.objects.filter(name=product_names, is_active=True)

            if not products.exists():
                self.stdout.write(
                    self.style.WARNING(f"No se encontró producto activo para: {product_names}")
                )
                continue

            # Procesar cada imagen
            for image_file in image_files:
                self.stdout.write(f"\n{'='*80}")
                self.stdout.write(self.style.SUCCESS(f"Imagen encontrada: {image_file.name}"))
                self.stdout.write(f"Carpeta: {folder_name}")

                if auto_mode:
                    # Modo automático: asociar a todos los productos de la categoría
                    for product in products:
                        self._link_image_to_product(image_file, product, folder_name)
                else:
                    # Modo interactivo
                    self.stdout.write("\nProductos disponibles:")
                    for idx, product in enumerate(products, 1):
                        self.stdout.write(f"  {idx}. {product.name}")

                    self.stdout.write(f"  a. Asociar a TODOS los productos listados")
                    self.stdout.write(f"  s. Saltar esta imagen")

                    choice = input("\nSelecciona una opción (número, 'a' para todos, 's' para saltar): ").strip()

                    if choice.lower() == 's':
                        self.stdout.write(self.style.WARNING("Imagen saltada"))
                        continue
                    elif choice.lower() == 'a':
                        for product in products:
                            self._link_image_to_product(image_file, product, folder_name)
                    else:
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(products):
                                product = list(products)[idx]
                                self._link_image_to_product(image_file, product, folder_name)
                            else:
                                self.stdout.write(self.style.ERROR("Opción inválida"))
                        except ValueError:
                            self.stdout.write(self.style.ERROR("Opción inválida"))

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(self.style.SUCCESS("\n✓ Proceso completado"))

    def _link_image_to_product(self, image_path, product, folder_name):
        """Asocia una imagen a un producto"""
        # Verificar si ya existe esta imagen para el producto
        relative_path = f"product_images/{image_path.name}"

        existing = ProductImage.objects.filter(
            product=product,
            image__endswith=image_path.name
        ).first()

        if existing:
            self.stdout.write(
                self.style.WARNING(f"  ⚠ Ya existe esta imagen para {product.name}")
            )
            return

        # Abrir el archivo de imagen
        with open(image_path, 'rb') as img_file:
            # Verificar si el producto ya tiene imágenes
            has_images = ProductImage.objects.filter(product=product).exists()
            is_primary = not has_images  # Primera imagen es la principal

            # Crear la imagen del producto
            product_image = ProductImage.objects.create(
                product=product,
                alt_text=f"{product.name}",
                is_primary=is_primary
            )

            # Guardar el archivo
            product_image.image.save(
                image_path.name,
                File(img_file),
                save=True
            )

            primary_text = " (Imagen Principal)" if is_primary else ""
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ Imagen asociada a: {product.name}{primary_text}")
            )
