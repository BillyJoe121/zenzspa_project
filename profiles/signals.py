from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ClientDoshaAnswer

@receiver([post_save, post_delete], sender=ClientDoshaAnswer)
def update_dominant_dosha_on_answer_change(sender, instance, **kwargs):
    """
    Señal que se dispara después de guardar o eliminar una respuesta del cuestionario Dosha.
    Llama al método para recalcular el Dosha dominante del perfil asociado.
    """
    # El 'instance' es el objeto ClientDoshaAnswer que fue guardado o eliminado.
    # Accedemos a su perfil clínico y llamamos al método de cálculo.
    profile = instance.profile
    profile.calculate_dominant_dosha()