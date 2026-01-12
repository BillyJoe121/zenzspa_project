from profiles.models import DoshaQuestion, DoshaOption

def run():
    # Crear pregunta de ejemplo
    if not DoshaQuestion.objects.exists():
        print("Creating Dosha questions...")
        q1 = DoshaQuestion.objects.create(
            text="¿Cómo describirías tu constitución física?",
            category="PHYSICAL",
            order=1,
            is_active=True
        )
        # Crear opciones
        DoshaOption.objects.create(
            question=q1,
            text="Delgado/a, estructura ósea ligera",
            associated_dosha="VATA",
            weight=3
        )
        DoshaOption.objects.create(
            question=q1,
            text="Complexión media, musculoso/a",
            associated_dosha="PITTA",
            weight=3
        )
        DoshaOption.objects.create(
            question=q1,
            text="Estructura sólida, tiende al sobrepeso",
            associated_dosha="KAPHA",
            weight=3
        )
        print("Questions created successfully.")
    else:
        print("Questions already exist.")

if __name__ == "__main__":
    run()
