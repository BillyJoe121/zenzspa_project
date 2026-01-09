from django.core.management.base import BaseCommand
from django.db import transaction

from profiles.models import DoshaQuestion, DoshaOption


DOSHA_QUESTIONS = [
    {
        "text": "¿Cómo es tu constitución física?",
        "category": "Físico",
        "order": 1,
        "is_active": True,
        "options": [
            {
                "text": "Delgado/a, con huesos prominentes, me cuesta ganar peso",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Constitución atlética y musculosa, peso moderado",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Constitución robusta y sólida, tiendo a ganar peso fácilmente",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu piel?",
        "category": "Físico",
        "order": 2,
        "is_active": True,
        "options": [
            {
                "text": "Piel seca, áspera, a veces fría al tacto",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Piel suave, cálida, propensa a enrojecimiento o irritaciones",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Piel gruesa, oleosa, suave y fresca",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo describirías tu cabello?",
        "category": "Físico",
        "order": 3,
        "is_active": True,
        "options": [
            {
                "text": "Cabello fino, seco, con tendencia a enredarse",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Cabello fino a moderado, graso, con tendencia a canas prematuras",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Cabello grueso, abundante, brillante y oleoso",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo son tus articulaciones?",
        "category": "Físico",
        "order": 4,
        "is_active": True,
        "options": [
            {
                "text": "Articulaciones que crujen, flexibles pero inestables",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Articulaciones moderadamente flexibles y estables",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Articulaciones firmes, fuertes, con buena lubricación",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo son tus ojos?",
        "category": "Físico",
        "order": 5,
        "is_active": True,
        "options": [
            {
                "text": "Ojos pequeños, secos, pestañeo frecuente",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Ojos de tamaño mediano, penetrantes, sensibles a la luz",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Ojos grandes, brillantes, pestañas largas",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo son tus manos y pies normalmente?",
        "category": "Físico",
        "order": 6,
        "is_active": True,
        "options": [
            {
                "text": "Manos y pies fríos la mayor parte del tiempo",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Manos y pies usualmente calientes",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Manos y pies frescos al tacto",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu apetito?",
        "category": "Digestivo",
        "order": 7,
        "is_active": True,
        "options": [
            {
                "text": "Apetito irregular, a veces tengo mucha hambre y otras ninguna",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Apetito fuerte y regular, me molesta saltarme comidas",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Apetito moderado, puedo pasar horas sin comer sin problema",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu digestión?",
        "category": "Digestivo",
        "order": 8,
        "is_active": True,
        "options": [
            {
                "text": "Digestión irregular, gases, hinchazón, estreñimiento variable",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Digestión rápida y eficiente, a veces acidez o sensación de ardor",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Digestión lenta y pesada, sensación de plenitud prolongada",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Qué tipo de alimentos prefieres?",
        "category": "Digestivo",
        "order": 9,
        "is_active": True,
        "options": [
            {
                "text": "Prefiero alimentos calientes, cocinados, y reconfortantes",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Me atraen alimentos fríos, frescos y bebidas heladas",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Disfruto comidas picantes, estimulantes y ligeras",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo son tus evacuaciones intestinales?",
        "category": "Digestivo",
        "order": 10,
        "is_active": True,
        "options": [
            {
                "text": "Evacuaciones irregulares, a veces estreñimiento, heces secas",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Evacuaciones regulares, 1-2 veces al día, heces blandas",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Evacuaciones lentas pero regulares, heces pesadas",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo aprendes mejor?",
        "category": "Mental",
        "order": 11,
        "is_active": True,
        "options": [
            {
                "text": "Aprendo rápido pero olvido fácilmente",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Aprendo con enfoque y retengo bien la información",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Aprendo lentamente pero una vez aprendido, nunca olvido",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu mente generalmente?",
        "category": "Mental",
        "order": 12,
        "is_active": True,
        "options": [
            {
                "text": "Mente activa y creativa, muchas ideas simultáneas",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Mente analítica, enfocada, orientada a objetivos",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Mente calmada, metódica, procesamiento tranquilo",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu memoria?",
        "category": "Mental",
        "order": 13,
        "is_active": True,
        "options": [
            {
                "text": "Memoria a corto plazo excelente, largo plazo irregular",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Buena memoria general, especialmente para detalles",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Memoria a largo plazo excepcional",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo tomas decisiones?",
        "category": "Mental",
        "order": 14,
        "is_active": True,
        "options": [
            {
                "text": "Tomo decisiones rápidamente pero a veces cambio de opinión",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Analizo y decido con determinación",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Necesito tiempo para decidir, pero luego soy firme",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu capacidad de concentración?",
        "category": "Mental",
        "order": 15,
        "is_active": True,
        "options": [
            {
                "text": "Me distraigo fácilmente, mente dispersa",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Alta concentración cuando algo me interesa",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Concentración sostenida y estable",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu manera de hablar?",
        "category": "Mental",
        "order": 16,
        "is_active": True,
        "options": [
            {
                "text": "Hablo rápido, mucho, a veces de manera desorganizada",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Hablo con claridad, de forma directa y persuasiva",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Hablo lento, pausado, con voz profunda",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Qué emociones experimentas con más frecuencia?",
        "category": "Emocional",
        "order": 17,
        "is_active": True,
        "options": [
            {
                "text": "Tiendo a sentir ansiedad, preocupación o miedo",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Tiendo a sentir frustración, irritabilidad o enojo",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Tiendo a sentir apego, resistencia al cambio o apatía",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo reaccionas bajo estrés?",
        "category": "Emocional",
        "order": 18,
        "is_active": True,
        "options": [
            {
                "text": "Me siento ansioso/a, disperso/a, con pensamientos acelerados",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Me irrito, me vuelvo crítico/a o confrontativo/a",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Me retiro, me vuelvo apático/a o evito situaciones",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo describirías tu temperamento general?",
        "category": "Emocional",
        "order": 19,
        "is_active": True,
        "options": [
            {
                "text": "Entusiasta, excitable, cambiante emocionalmente",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Apasionado/a, intenso/a, competitivo/a",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Tranquilo/a, amoroso/a, complaciente",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo expresas tus emociones?",
        "category": "Emocional",
        "order": 20,
        "is_active": True,
        "options": [
            {
                "text": "Expreso emociones intensamente pero cambian rápido",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Expreso emociones con intensidad y las sostengo",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Guardo emociones, tardo en expresarlas",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo te adaptas al cambio?",
        "category": "Emocional",
        "order": 21,
        "is_active": True,
        "options": [
            {
                "text": "Me adapto rápido al cambio, incluso lo disfruto",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Acepto el cambio si tiene sentido lógico",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Prefiero la estabilidad, el cambio me incomoda",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo son tus niveles de energía?",
        "category": "Energía",
        "order": 22,
        "is_active": True,
        "options": [
            {
                "text": "Energía en ráfagas, variable durante el día",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Energía constante y sostenida",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Energía estable pero necesito motivación para activarme",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo es tu sueño?",
        "category": "Energía",
        "order": 23,
        "is_active": True,
        "options": [
            {
                "text": "Sueño ligero, irregular, me cuesta conciliar el sueño",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Sueño moderado, me despierto fácil, duermo 6-8 horas",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Sueño profundo, prolongado, me cuesta despertar",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo reaccionas a la temperatura ambiente?",
        "category": "Temperatura",
        "order": 24,
        "is_active": True,
        "options": [
            {
                "text": "Sensible al frío, prefiero ambientes cálidos",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Sensible al calor, prefiero ambientes frescos",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Tolero bien ambas, pero prefiero calor moderado",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    },
    {
        "text": "¿Cómo describirías tu estilo de vida?",
        "category": "Comportamiento",
        "order": 25,
        "is_active": True,
        "options": [
            {
                "text": "Activo/a, inquieto/a, necesito movimiento constante",
                "associated_dosha": "VATA",
                "weight": 1
            },
            {
                "text": "Orientado/a a metas, competitivo/a, estructurado/a",
                "associated_dosha": "PITTA",
                "weight": 1
            },
            {
                "text": "Calmado/a, metódico/a, disfruto la rutina",
                "associated_dosha": "KAPHA",
                "weight": 1
            }
        ]
    }
]

__all__ = ["DOSHA_QUESTIONS"]
