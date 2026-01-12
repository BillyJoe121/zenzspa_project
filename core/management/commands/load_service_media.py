"""
Management command para cargar imágenes y videos de servicios desde GitHub.
Uso: python manage.py load_service_media
"""

from django.core.management.base import BaseCommand
from spa.models import Service, ServiceMedia


class Command(BaseCommand):
    help = "Carga imágenes y videos de servicios desde GitHub"

    # Mapeo de servicios a sus medios (URLs de GitHub)
    # Imágenes optimizadas en formato WebP (98% más ligeras)
    SERVICE_MEDIA_MAPPING = {
        "Cráneo Facial Ensueño": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialEnsueño/spa-massage-2025-12-17-13-19-57-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialEnsueño/stress-be-gone-shot-of-a-beautiful-young-woman-en-2026-01-09-10-20-05-utc.webp",
            ],
        },
        "Cráneo Facial Ocaso": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialOcaso/woman-receiving-massage-relaxing-2025-12-17-06-58-04-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialOcaso/cropped-shot-of-a-young-woman-enjyoing-a-massage-a-2026-01-09-10-57-13-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialOcaso/cropped-view-of-masseurs-doing-massage-to-woman-an-2026-01-06-00-44-09-utc.webp",
            ],
        },
        "Cráneo Facial Renacer": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialRenacer/women-s-healing-massage-2025-12-17-14-44-21-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialRenacer/beautiful-woman-relaxing-and-getting-head-massage-2026-01-06-09-19-43-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/CraneoFacialRenacer/beautiful-young-woman-relaxing-with-head-massage-2026-01-07-00-41-33-utc.webp",
            ],
        },
        "Drenaje Linfático": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/DrenajeLinfatico/hand-massage-2025-12-17-08-49-02-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/DrenajeLinfatico/ayurveda-stomach-massage-2026-01-05-22-56-01-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/DrenajeLinfatico/masseur-doing-massage-on-woman-body-in-the-spa-sal-2025-10-15-21-57-09-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/DrenajeLinfatico/shes-leaving-her-troubles-behind-cropped-shot-of-2026-01-09-10-05-07-utc.webp",
            ],
        },
        "Experiencia Zen": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ExperienciaZen/aromatherapy-massage-hand-massage-beauty-technique-2025-12-17-05-07-02-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ExperienciaZen/massaging-the-body-and-mind-2026-01-09-09-37-58-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ExperienciaZen/spa-serenity-2026-01-09-10-03-30-utc.webp",
            ],
        },
        "Herbal Essence": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HerbalEssence/physiotherapist-uses-vibrating-massager-for-massag-2025-12-17-09-29-35-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HerbalEssence/arm-massage-2026-01-05-06-08-10-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HerbalEssence/arm-sports-massage-physical-therapy-2026-01-05-06-11-49-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HerbalEssence/leg-massage-physical-therapyst-massaging-leg-of-y-2026-01-05-06-33-08-utc.webp",
            ],
        },
        "Hidra Facial": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HidraFacial/closeup-of-a-woman-receiving-a-hydromicrodermabras-2025-12-17-04-50-44-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HidraFacial/experienced-cosmetologist-preparing-to-apply-facia-2026-01-05-22-48-36-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HidraFacial/happy-calm-relaxed-young-woman-or-teenage-girl-lyi-2026-01-08-07-49-31-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/HidraFacial/young-girl-gets-a-cosmetic-injection-2026-01-07-00-37-54-utc.webp",
            ],
        },
        "Limpieza Facial Sencilla": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/LimpiezaFacialSencilla/facial-skin-cleaning-with-gel-mask-at-beauty-parlo-2025-12-17-03-30-40-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/LimpiezaFacialSencilla/face-cleansing-2026-01-05-06-35-19-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/LimpiezaFacialSencilla/face-cupping-therapy-ventosa-cupping-treatment-fo-2026-01-05-06-34-33-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/LimpiezaFacialSencilla/massaging-face-2026-01-05-06-11-43-utc.webp",
            ],
        },
        "Pediluvio": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Pediluvio/masseur-massaging-woman-feet-in-spa-closeup-of-fe-2025-12-17-14-15-33-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Pediluvio/close-up-foot-reflexology-2026-01-09-01-12-47-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Pediluvio/man-having-a-pedicure-2026-01-09-11-39-04-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Pediluvio/relaxing-foot-massage-2026-01-09-09-22-11-utc.webp",
            ],
        },
        "Terapéutico Completo": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoCompleto/senior-having-professional-massage-2025-12-17-05-38-55-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoCompleto/caucasian-woman-receiving-a-leg-massage-on-spa-the-2026-01-07-00-38-44-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoCompleto/chiropractor-doing-manual-adjustment-on-woman-shou-2026-01-09-15-04-43-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoCompleto/relaxing-shoulders-and-neck-massage-2026-01-05-23-01-58-utc.webp",
            ],
        },
        "Terapéutico Focalizado": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoFocalizado/massage-2025-12-17-07-09-01-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoFocalizado/ayurveda-buttocks-massage-2026-01-05-22-56-08-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoFocalizado/close-up-of-therapist-doing-anti-cellulite-madero-2026-01-05-06-09-29-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoFocalizado/relaxing-shoulders-and-back-massage-2026-01-05-22-48-57-utc.webp",
            ],
        },
        "Terapéutico Mixto": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoMixto/hands-spa-massage-and-woman-at-wellness-resort-r-2025-12-17-11-42-27-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoMixto/ayurveda-stomach-massage-2026-01-05-06-10-32-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoMixto/therapist-massaging-client-s-jaw-jaw-realignement-2026-01-05-23-01-39-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapeuticoMixto/women-s-self-care-back-and-neck-massage-with-speci-2026-01-09-09-56-24-utc.webp",
            ],
        },
        "Terapia de Equilibrio": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapiaDeEquilibrio/massage-2025-12-17-07-34-28-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapiaDeEquilibrio/masseur-doing-massage-on-woman-body-in-the-spa-sal-2026-01-06-09-21-56-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapiaDeEquilibrio/selective-focus-of-masseur-doing-massage-to-attrac-2026-01-09-12-22-21-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/TerapiaDeEquilibrio/womans-healthy-body-getting-massage-in-the-spa-sal-2026-01-07-00-40-19-utc.webp",
            ],
        },
        "Toque de Seda": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ToqueDeSeda/therapy-spa-and-woman-relax-with-massage-for-heal-2025-12-17-08-46-12-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ToqueDeSeda/cryo-massage-wrist-pain-2026-01-05-23-02-22-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ToqueDeSeda/this-could-be-you-2026-01-09-09-39-26-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ToqueDeSeda/tibetan-bells-in-sound-therapy-2026-01-05-22-46-24-utc.webp",
            ],
        },
        "Udvartana": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Udvartana/massage-therapist-doing-spa-massage-with-massage-t-2025-12-17-22-39-09-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Udvartana/masseuse-making-thai-yoga-massage-treatment-stret-2026-01-07-01-02-56-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Udvartana/masseuse-making-thai-yoga-massage-treatment-stret-2026-01-07-01-02-57-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/Udvartana/stimulation-of-pericardium-improving-wellbeing-m-2026-01-05-06-12-59-utc.webp",
            ],
        },
        "Zen Extendido": {
            "video": "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ZenExtendido/body-massage-in-the-massage-room-back-massage-2025-12-17-16-45-50-utc.mp4",
            "images": [
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ZenExtendido/chocolate-body-massage-beauty-treatment-with-rich-2026-01-05-06-23-33-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ZenExtendido/hot-stone-massage-2026-01-05-22-52-33-utc.webp",
                "https://github.com/BillyJoe121/StudiozensImages/blob/main/Servicios/ZenExtendido/kizhi-massage-or-herbal-bolus-bags-ayurveda-massag-2026-01-05-06-32-42-utc.webp",
            ],
        },
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Limpia todos los medios existentes antes de cargar",
        )

    def handle(self, *args, **options):
        clear_existing = options["clear"]

        if clear_existing:
            self.stdout.write("Limpiando medios existentes...")
            # Limpiar main_media_url de todos los servicios
            Service.objects.all().update(main_media_url=None, is_main_media_video=False)
            # Eliminar todos los ServiceMedia
            ServiceMedia.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("[OK] Medios limpiados\n"))

        total_services = len(self.SERVICE_MEDIA_MAPPING)
        processed = 0
        errors = 0

        self.stdout.write(f"Cargando medios para {total_services} servicios...\n")

        for service_name, media_data in self.SERVICE_MEDIA_MAPPING.items():
            try:
                # Buscar el servicio
                service = Service.objects.get(name=service_name)

                # Convertir URLs de GitHub a URLs raw
                video_url = self._convert_to_raw_url(media_data["video"])
                image_urls = [self._convert_to_raw_url(url) for url in media_data["images"]]

                # Actualizar el video principal
                service.main_media_url = video_url
                service.is_main_media_video = True
                service.save()

                self.stdout.write(
                    self.style.SUCCESS(f"[OK] Video principal cargado para: {service_name}")
                )

                # Eliminar ServiceMedia existentes para este servicio si no se limpiaron antes
                if not clear_existing:
                    ServiceMedia.objects.filter(service=service).delete()

                # Crear ServiceMedia para las imágenes
                for idx, image_url in enumerate(image_urls):
                    ServiceMedia.objects.create(
                        service=service,
                        media_url=image_url,
                        media_type=ServiceMedia.MediaType.IMAGE,
                        alt_text=f"{service_name} - Imagen {idx + 1}",
                        display_order=idx,
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"[OK] {len(image_urls)} imagen(es) secundaria(s) cargada(s) para: {service_name}\n"
                    )
                )

                processed += 1

            except Service.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"[WARNING] Servicio no encontrado: {service_name}")
                )
                errors += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"[ERROR] Error procesando {service_name}: {str(e)}")
                )
                errors += 1

        # Resumen final
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS(f"\n[OK] Proceso completado"))
        self.stdout.write(f"  - Servicios procesados: {processed}/{total_services}")
        if errors > 0:
            self.stdout.write(self.style.WARNING(f"  - Errores: {errors}"))
        self.stdout.write("")

    def _convert_to_raw_url(self, github_url):
        """
        Convierte una URL de GitHub del formato:
        https://github.com/user/repo/blob/main/path/file.ext
        a:
        https://github.com/user/repo/raw/main/path/file.ext

        Usa /raw/ en lugar de raw.githubusercontent.com para mejor soporte CORS
        """
        return github_url.replace("/blob/", "/raw/")
