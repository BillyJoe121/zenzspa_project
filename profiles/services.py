from .models import ClinicalProfile, ClientDoshaAnswer, Dosha

def calculate_dominant_dosha_and_element(profile_id: str):
    """
    Calcula el Dosha y Elemento dominantes de un perfil basado en sus respuestas,
    y actualiza el perfil en la base de datos.

    Args:
        profile_id: El ID (UUID) del ClinicalProfile a calcular.

    Returns:
        Un diccionario con el resultado del cálculo.
    """
    try:
        profile = ClinicalProfile.objects.get(id=profile_id)
    except ClinicalProfile.DoesNotExist:
        return {"error": "Perfil no encontrado."}

    answers = ClientDoshaAnswer.objects.filter(profile=profile).select_related('selected_option')

    if not answers.exists():
        return {"error": "El perfil no tiene respuestas para calcular el Dosha."}

    scores = {
        Dosha.VATA: 0,
        Dosha.PITTA: 0,
        Dosha.KAPHA: 0,
    }

    # 1. Calcular la puntuación total
    for answer in answers:
        option = answer.selected_option
        dosha_type = option.associated_dosha
        weight = option.weight
        
        if dosha_type in scores:
            scores[dosha_type] += weight

    # 2. Determinar el Dosha dominante
    if not any(scores.values()): # Si todas las puntuaciones son 0
        dominant_dosha = Dosha.UNKNOWN
    else:
        dominant_dosha = max(scores, key=scores.get)
    
    # 3. Determinar el Elemento basado en el Dosha dominante
    element_map = {
        Dosha.VATA: ClinicalProfile.Element.AIR,
        Dosha.PITTA: ClinicalProfile.Element.FIRE,
        Dosha.KAPHA: ClinicalProfile.Element.EARTH,
    }
    dominant_element = element_map.get(dominant_dosha)

    # 4. Actualizar el Perfil Clínico
    profile.dosha = dominant_dosha
    if dominant_element:
        profile.element = dominant_element
    profile.save(update_fields=['dosha', 'element'])

    return {
        "dominant_dosha": dominant_dosha,
        "dominant_element": dominant_element,
        "scores": scores
    }