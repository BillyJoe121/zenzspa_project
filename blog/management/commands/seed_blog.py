from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.core.files.base import ContentFile
from blog.models import Category, Tag, Article
import random
import requests
import os


class Command(BaseCommand):
    help = 'Pobla el blog con los artículos definitivos y descarga las imágenes'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Eliminando datos existentes del blog...'))
        Article.objects.all().delete()
        Category.objects.all().delete()
        Tag.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✓ Datos anteriores eliminados.'))

        # Datos de los artículos definitivos
        articles_data = [
            {
                "title": "Masajes relajantes en Cali: beneficios reales y cuándo deberías hacerte uno",
                "slug": "masajes-relajantes-cali-beneficios-reales",
                "subtitle": "Más que un lujo, una necesidad para tu salud mental y física en medio del caos de la ciudad.",
                "excerpt": "¿Sientes que el estrés te gana la batalla? Descubre por qué un masaje en Studio Zens no es solo 'sentirse bien', es reiniciar tu sistema nervioso. Te contamos cuándo tu cuerpo te está pidiendo a gritos una pausa.",
                "content": "<h2>Vivir en Cali: Un ritmo vibrante que también agota</h2><p>Amamos nuestra ciudad, la brisa de la tarde y la alegría de nuestra gente. Pero seamos sinceras, el tráfico de la hora pico, el calor del mediodía y las responsabilidades diarias pueden convertir ese ritmo vibrante en una carga pesada sobre nuestros hombros (literalmente). A veces, entre el trabajo y la casa, olvidamos que nuestro cuerpo no es una máquina, es un templo que necesita mantenimiento y, sobre todo, mucho cariño.</p><p>En <strong>Studio Zens</strong>, ubicado en el tranquilo <strong>Barrio La Cascada</strong>, vemos a diario cómo muchas personas llegan buscando solo 'quitarse un dolor', cuando en realidad necesitan desconectar para volver a conectar.</p><h2>Beneficios reales: Lo que pasa en tu cuerpo cuando te dejas cuidar</h2><p>Cuando hablamos de masajes, no nos referimos solo a que te toquen la espalda. Hablamos de ciencia aplicada al bienestar. ¿Sabías que servicios como nuestra <strong>Experiencia Zen</strong> o el <strong>Toque de Seda</strong> están diseñados para bajar los niveles de cortisol (la hormona del estrés)?</p><ul><li><strong>Alivio muscular profundo:</strong> Con técnicas como el <strong>Terapéutico Mixto</strong> o <strong>Focalizado</strong>, ayudamos a movilizar esa tensión acumulada por las malas posturas frente al computador.</li><li><strong>Detox natural:</strong> Terapias como el <strong>Drenaje Linfático</strong> o el exótico <strong>Udvartana</strong> ayudan a tu cuerpo a eliminar lo que no necesita, haciéndote sentir más ligera.</li><li><strong>Equilibrio mental:</strong> Es un momento para apapachar tu mente. Al entrar en un estado de relajación profunda, tu sistema nervioso se resetea, mejorando tu calidad de sueño esa misma noche.</li></ul><h2>5 Señales de que necesitas agendar una cita HOY</h2><p>Tu cuerpo habla, y a veces grita. Si te identificas con dos o más de estos puntos, es hora de visitarnos en la Carrera 64:</p><ol><li><strong>Irritabilidad constante:</strong> Si todo te molesta, necesitas bajar las revoluciones.</li><li><strong>Insomnio:</strong> Das vueltas en la cama pensando en pendientes.</li><li><strong>Dolor de cabeza tensional:</strong> Esa presión en la nuca o detrás de los ojos.</li><li><strong>Piel apagada:</strong> El estrés se nota en el rostro (¡un <strong>Facial Hidra-limpieza</strong> caería perfecto aquí!).</li><li><strong>Simplemente no recuerdas cuándo fue la última vez que hiciste algo solo para ti.</strong></li></ol><h2>Tu refugio en La Cascada</h2><p>En Studio Zens no somos un sitio de paso, somos tu santuario. Contamos con duchas privadas para que puedas venir antes o después de tu jornada, y estacionamiento exclusivo para que no te estreses buscando dónde dejar el carro. Nos tomamos muy en serio tu bienestar, por eso nuestros terapeutas son expertos que respetan tu privacidad y confort en todo momento.</p><p>Recuerda, no necesitas estar 'enferma' para querer sentirte mejor. Ven a consentirte, a equilibrar tu energía y a darle a tu cuerpo el respeto que merece.</p><p><em>¿Lista para agendar? Visita nuestra sección de reservas en la web, elige tu terapia ideal y el horario que mejor te convenga. ¡Te esperamos con los aceites listos y las manos cálidas!</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/masseuse-applying-body-scrub-on-black-girl-back-2025-03-18-19-24-17-utc.jpg?raw=true",
                "category": "Bienestar",
                "tags": [
                    "Masajes Cali",
                    "Spa La Cascada",
                    "Estrés",
                    "Salud Mental",
                    "Studio Zens",
                    "Dolor de espalda",
                    "Autocuidado"
                ],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": True,
                "reading_time_minutes": 4,
                "meta_title": "Masajes Relajantes en Cali | Studio Zens Spa - La Cascada",
                "meta_description": "¿Buscas masajes en Cali? Studio Zens: reduce estrés y mejora salud con terapias profesionales. Estacionamiento y duchas disponibles.",
                "custom_seo_keywords": "masajes cali sur, spa barrio la cascada, masaje relajante cali, drenaje linfatico cali, studio zens precios"
            },
            {
                "title": "Faciales profesionales en Cali: tipos, beneficios y cada cuánto hacerlos",
                "slug": "faciales-profesionales-cali-tipos-beneficios",
                "subtitle": "Porque tu rostro cuenta una historia, asegúrate de que sea una de luminosidad y descanso.",
                "excerpt": "El clima de Cali y la contaminación pueden apagar tu brillo natural. Descubre la diferencia entre lavarte la cara y una Hidra-limpieza profesional en Studio Zens. Te decimos cuándo es el momento ideal para agendar.",
                "content": "<h2>Cali, el calor y tu piel: Una relación complicada</h2><p>Vivir en nuestra amada Cali tiene sus privilegios, pero el calorcito constante, la humedad y la polución del día a día son desafíos reales para nuestro rostro. A veces nos miramos al espejo y notamos la piel opaca, con puntitos negros o simplemente con una textura que grita '¡necesito ayuda!'. Lavarnos la cara en casa es vital, pero hay momentos donde tu piel necesita manos expertas y productos profesionales para volver a respirar.</p><h2>¿Por qué un facial profesional en Studio Zens?</h2><p>Muchas creen que un facial es solo ponerse cremitas, pero en <strong>Studio Zens</strong>, ubicado en el corazón del <strong>Barrio La Cascada</strong>, llevamos la experiencia a otro nivel. No somos dermatólogos (y siempre te recomendaremos ir a uno si vemos algo clínico), pero somos expertas en bienestar estético y relajación.</p><p>Un facial profesional limpia a profundidad lo que el jabón no alcanza, estimula la circulación y, lo más importante, es un momento de pausa. Imagina liberar no solo las impurezas de tus poros, sino también la tensión que acumulas en el entrecejo o la mandíbula.</p><h2>Tipos de experiencias para tu rostro</h2><p>En nuestro menú de servicios <em>Spa</em>, hemos diseñado opciones que van más allá de la estética tradicional:</p><ul><li><strong>Limpieza Facial / Hidra-limpieza:</strong> Perfectas para cuando sientes la piel cargada. Utilizamos aparatología suave y productos de alta calidad para descongestionar, hidratar profundamente y devolverle a tu piel ese efecto 'jugoso' y sano que tanto nos gusta.</li><li><strong>Craneo facial (Ensueño / Ocaso / Renacer):</strong> ¿Sabías que acumulamos mucho estrés en los músculos de la cara y la cabeza? Estas sesiones no son solo para la piel, son para el alma. Combinamos técnicas de masaje relajante en rostro, cabeza y cuello para que salgas flotando. Es el complemento ideal si sufres de dolores de cabeza tensionales o bruxismo leve por estrés.</li></ul><h2>¿Cada cuánto debería hacerme uno?</h2><p>Esta es la pregunta del millón. La respuesta sabia es: escucha a tu piel. Sin embargo, el ciclo de renovación celular natural ocurre aproximadamente cada 28 días. Por eso, nuestra recomendación de oro es regalarte una <strong>limpieza facial profunda una vez al mes</strong>.</p><p>Hacerlo con esta frecuencia ayuda a mantener los poros limpios, previene el envejecimiento prematuro y asegura que los productos que usas en casa (serums, cremas) realmente penetren y funcionen.</p><h2>Tu momento de brillo en el sur de Cali</h2><p>Recuerda que en <strong>Studio Zens</strong> (Carrera 64 #1c-87) todo está pensado para tu comodidad. Tenemos estacionamiento privado para que llegues tranquila y te desconectes del mundo exterior. No necesitas traer nada, solo las ganas de verte y sentirte radiante.</p><p><em>¿Lista para recuperar tu 'glow'? Entra ahora a nuestra web, busca la sección de Agendamiento y reserva tu cita. ¡Tu piel te lo va a agradecer cada vez que te mires al espejo!</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/woman-indulges-in-a-luxurious-skincare-treatment-w-2024-10-18-22-35-38-utc.jpg?raw=true",
                "category": "Spa",
                "tags": [
                    "Limpieza Facial Cali",
                    "Cuidado de la piel",
                    "Hidra facial",
                    "Masaje Craneofacial",
                    "Studio Zens",
                    "Belleza Cali"
                ],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 5,
                "meta_title": "Faciales y Limpieza Facial en Cali | Studio Zens",
                "meta_description": "¿Buscas limpieza facial en Cali? Studio Zens ofrece Hidra-limpiezas y masajes para renovar tu piel. Reserva online tu cita en La Cascada.",
                "custom_seo_keywords": "limpieza facial profunda cali, spa facial cali sur, masaje cara y cuello, hidratacion facial cali, agendar cita studio zens"
            },
            {
                "title": "¿Cada cuánto hacerse un facial? Recomendaciones para el clima de Cali",
                "slug": "frecuencia-faciales-clima-cali",
                "subtitle": "El calor, la brisa y la humedad juegan un papel clave en tu rutina. Aprende a adaptar tus visitas al spa.",
                "excerpt": "Cali es hermosa, pero su clima puede ser intenso para tu rostro. ¿Grasa, poros abiertos o resequedad por el aire acondicionado? Te guiamos para encontrar tu frecuencia ideal en Studio Zens.",
                "content": "<h2>Cali: Eterna primavera, eterno reto para tu piel</h2><p>Vivir en la 'Sucursal del Cielo' es un privilegio, pero seamos honestas: nuestro clima es un arma de doble filo para el cutis. El calor del mediodía estimula la producción de sebo (ese brillito que no siempre queremos), y la contaminación del tráfico se adhiere fácilmente a una piel húmeda. Además, pasamos del calor de la calle al aire acondicionado de la oficina, y esos cambios bruscos deshidratan nuestra barrera natural.</p><p>Por eso, en <strong>Studio Zens</strong>, creemos que la regla general de 'un facial al mes' tiene sus matices cuando vives en Cali.</p><h2>La regla de oro: El ciclo de 28 días</h2><p>Nuestra piel se renueva naturalmente cada 28 días, aproximadamente. Las células muertas suben a la superficie y, si no las retiramos, tapan los poros, opacan tu rostro y evitan que tus cremas caras funcionen. Una <strong>Limpieza Facial Profunda</strong> o una <strong>Hidra-limpieza</strong> profesional ayudan a completar ese ciclo.</p><h2>¿Cuál es tu frecuencia ideal según tu tipo de piel?</h2><p>Aquí en el <strong>Barrio La Cascada</strong>, nuestras terapeutas han notado patrones claros:</p><ul><li><strong>Pieles Mixtas o Grasas (Muy común en Cali):</strong> Si sientes que a la mitad del día tu zona T brilla más que el sol caleño, te recomendamos visitarnos <strong>cada 3 o 4 semanas</strong>. Necesitamos mantener los poros descongestionados para evitar brotes.</li><li><strong>Pieles Secas o Maduras:</strong> Si el aire acondicionado te deja la piel tirante, una visita <strong>cada 4 a 6 semanas</strong> es ideal. Aquí el enfoque es la hidratación profunda y el 'mimo' que ofrecen nuestros masajes faciales.</li><li><strong>Pieles Normales:</strong> ¡Afortunada! Una vez al mes es perfecto para mantener ese equilibrio envidiable.</li></ul><h2>Más que limpieza, es tu momento Zen</h2><p>Recuerda que en Studio Zens, un facial no es solo extracción. Es una experiencia de nuestra categoría <em>Spa</em>. Mientras tu piel se renueva con nuestra tecnología de Hidra-limpieza, tú te relajas en un ambiente seguro, privado y fresco, lejos del ruido de la ciudad.</p><h2>Agenda tu cita de mantenimiento</h2><p>No esperes a tener un evento especial para cuidar de ti. La constancia es el secreto de esa piel de porcelana. Estamos en la Carrera 64 #1c-87, con estacionamiento listo para ti.</p><p><em>¿No sabes qué necesita tu piel hoy? Entra a nuestra web, explora las opciones de Limpieza Facial e Hidra y reserva tu espacio en el calendario. ¡Es fácil, rápido y tu yo del futuro te lo agradecerá!</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/beauty-water-and-woman-cleaning-face-for-body-hyg-2025-04-06-08-52-05-utc.jpg?raw=true",
                "category": "Spa",
                "tags": [
                    "Cuidado facial Cali",
                    "Piel grasa",
                    "Hidra limpieza",
                    "Clima de Cali",
                    "Rutina de belleza",
                    "Studio Zens"
                ],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 4,
                "meta_title": "Frecuencia Limpieza Facial en Cali | Studio Zens",
                "meta_description": "El clima de Cali afecta tu piel. Descubre la frecuencia ideal para una limpieza facial según tu tipo de piel. Expertas en Studio Zens, La Cascada.",
                "custom_seo_keywords": "limpieza facial piel grasa cali, hidra limpieza facial cali, faciales barrio la cascada, frecuencia limpieza facial, spa cali sur"
            },
            {
                "title": "Masaje relajante vs. masaje descontracturante: diferencias y cuál elegir en Cali",
                "slug": "diferencia-masaje-relajante-descontracturante-cali",
                "subtitle": "¿Buscas desconectarte del mundo o aliviar ese dolor de espalda que no te deja en paz? Te ayudamos a decidir.",
                "excerpt": "Es la pregunta más común en nuestro spa. Muchas veces pedimos un relajante cuando necesitamos soltar nudos, o viceversa. Aquí te explicamos la diferencia real y cuál es el ideal para ti.",
                "content": "<h2>La eterna duda al reservar tu cita</h2><p>Llegas a la recepción (o estás frente a nuestra web de reservas) y te detienes un segundo: <em>'¿Qué necesito hoy? ¿Algo suave para dormir mejor o que me quiten este 'mico' que tengo trepado en el hombro?'</em>. Es la duda más común que recibimos en <strong>Studio Zens</strong>.</p><p>Vivimos en una ciudad activa como Cali, donde el estrés del tráfico en la Pasoancho o las largas jornadas frente al computador nos pasan factura de formas distintas. Por eso, entender la diferencia es clave para que salgas de nuestra camilla sintiéndote renovada.</p><h2>El Masaje Relajante: Un abrazo para tu sistema nervioso</h2><p>Piensa en servicios como nuestra <strong>Experiencia Zen</strong> o el exclusivo <strong>Toque de Seda</strong>. El objetivo aquí no es 'arreglar' un músculo dolorido, sino <strong>sedar</strong> tus sentidos.</p><ul><li><strong>¿Cómo se siente?</strong> Son maniobras fluidas, largas y con una presión de suave a media. El ritmo es lento y monótono (en el buen sentido) para invitarte al sueño.</li><li><strong>¿Para quién es?</strong> Si sientes agotamiento mental, ansiedad, insomnio o simplemente quieres un mimo porque te lo mereces. Es pura desconexión.</li></ul><h2>El Masaje Descontracturante (Terapéutico): Alivio real</h2><p>Aquí entran nuestros protocolos estrella: <strong>Terapéutico Completo</strong> y <strong>Terapéutico Focalizado</strong>. Aquí vamos a trabajar sobre la fibra muscular profunda.</p><ul><li><strong>¿Cómo se siente?</strong> La presión es más firme y puntual. Buscamos esos 'nudos' (contracturas) que limitan tu movimiento. Ojo: en Studio Zens creemos que un buen masaje terapéutico puede doler un poquito (ese 'dolor rico' de alivio), pero nunca debe ser una tortura.</li><li><strong>¿Para quién es?</strong> Si tienes dolor de espalda baja, cuello rígido ('tortícolis'), o pasas muchas horas sentada. Si sientes que cargas una mochila invisible, este es el tuyo.</li></ul><h2>¿Y si quiero los dos? El secreto de Studio Zens</h2><p>Aquí está el truco de experta: A veces el cuerpo necesita un poco de ambos. Por eso, en nuestro menú creamos el <strong>Terapéutico Mixto</strong>. Es nuestro <em>best-seller</em> porque combina la técnica precisa para soltar la tensión muscular con momentos de fluidez relajante para que no salgas adolorida, sino flotando.</p><h2>Tu decisión en el Barrio La Cascada</h2><p>Ya sea que elijas disolver el estrés o atacar el dolor, en nuestra sede en la Carrera 64 #1c-87 estamos listas para recibirte. Recuerda que contamos con terapeutas expertas que sabrán leer tu cuerpo, y duchas privadas por si necesitas refrescarte después de liberar todas esas toxinas.</p><p><em>¿Ya sabes cuál necesita tu cuerpo hoy? Visita nuestra web ahora mismo, selecciona tu categoría (¿Spa o Integral?) y asegura tu espacio. ¡Tu espalda y tu mente te lo piden a gritos!</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/woman-experiencing-the-benefits-of-an-expertly-con-2025-02-22-16-53-33-utc.jpg?raw=true",
                "category": "Integrales",
                "tags": [
                    "Masaje descontracturante Cali",
                    "Masaje relajante",
                    "Dolor de espalda",
                    "Terapéutico Mixto",
                    "Studio Zens",
                    "Salud y Bienestar"
                ],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 5,
                "meta_title": "Masaje Relajante vs Descontracturante en Cali | Studio Zens",
                "meta_description": "¿No sabes si elegir masaje relajante o descontracturante? En Studio Zens Cali te explicamos las diferencias y te recomendamos el ideal para tu dolor o estrés.",
                "custom_seo_keywords": "masaje terapeutico cali, masaje tejido profundo, diferencia masaje relax y descontracturante, spa la cascada cali precios, masaje para dolor de cuello"
            },
            {
                "title": "¿Un masaje realmente ayuda al estrés y la ansiedad? Lo que sí y lo que no",
                "slug": "masaje-estres-ansiedad-verdad-mitos-cali",
                "subtitle": "Separamos la magia de la ciencia. Entiende cómo tu cuerpo reacciona al tacto profesional y cuándo es tu mejor aliado.",
                "excerpt": "Todo el mundo dice 'necesito un masaje' cuando está estresado, pero ¿sabes por qué funciona? Te explicamos cómo terapias como la Experiencia Zen impactan tu sistema nervioso y cuáles son los límites reales.",
                "content": "<h2>El estrés en Cali no es solo tráfico</h2><p>Vivimos tiempos acelerados. Entre el trabajo, la familia y el ritmo de nuestra ciudad, es normal sentir que la mente no para. A menudo, esa ansiedad se manifiesta en el cuerpo: dolor en el cuello, mandíbula apretada (bruxismo) o esa sensación de 'nudo' en el estómago. En <strong>Studio Zens</strong>, recibimos a diario a mujeres y hombres buscando un respiro, pero nos gusta ser muy honestas sobre lo que nuestras manos pueden (y no pueden) hacer por ti.</p><h2>Lo que SÍ hace un masaje por tu ansiedad</h2><p>No es magia, es biología pura. Cuando recibes un servicio profesional, como nuestra <strong>Experiencia Zen</strong> o un <strong>Terapéutico Completo</strong>, suceden cosas maravillosas bajo tu piel:</p><ul><li><strong>Baja el volumen del Cortisol:</strong> El cortisol es la hormona del estrés. Estudios demuestran que un buen masaje puede reducir sus niveles significativamente, permitiendo que tu cuerpo salga del modo 'alerta' o 'huida'.</li><li><strong>El poder del tacto seguro:</strong> Al sentir el contacto profesional y respetuoso, tu cerebro libera oxitocina y serotonina. Es como recibir un abrazo que le dice a tu sistema nervioso: 'Ya estás a salvo, puedes descansar'.</li><li><strong>Rompe el ciclo del dolor-tensión:</strong> La ansiedad tensa los músculos, y el dolor muscular genera más ansiedad. Al soltar esos nudos con un masaje, interrumpimos ese círculo vicioso.</li></ul><h2>Lo que NO hace (y es importante saberlo)</h2><p>Queremos ser tu lugar seguro en el <strong>Barrio La Cascada</strong>, y parte de eso es la transparencia:</p><ul><li><strong>No es una cura médica:</strong> Un masaje es una herramienta de apoyo increíble, pero no reemplaza la terapia psicológica ni el tratamiento médico si sufres de un trastorno de ansiedad clínico.</li><li><strong>No soluciona el problema externo:</strong> Al salir del spa, el tráfico de la Pasoancho seguirá ahí. La diferencia es que <strong>tú</strong> estarás diferente: más calmada, con la mente más clara y con mejor disposición para enfrentar el caos.</li></ul><h2>¿Cuál elegir si mi mente no para?</h2><p>Si tu objetivo principal es calmar la ansiedad y el ruido mental, te recomendamos alejarte de los masajes muy fuertes al principio. Opta por:</p><ul><li><strong>Experiencia Zen:</strong> Suave, envolvente, perfecta para desconectar.</li><li><strong>Craneo facial (Ensueño):</strong> Ideal si piensas demasiado; trabajar la cabeza y el rostro induce una relajación casi hipnótica.</li><li><strong>Toque de Seda:</strong> Una caricia para el alma que te ayuda a reconectar con tu cuerpo de forma amable.</li></ul><h2>Tu refugio seguro en Cali</h2><p>Sabemos que cuando uno tiene ansiedad, ir a un lugar nuevo puede dar nervios. En Studio Zens (Carrera 64 #1c-87) te garantizamos un ambiente de respeto absoluto. Nuestros terapeutas son profesionales uniformados y éticos; aquí vienes a sanar, no a sentirte incómoda.</p><p><em>Si sientes que necesitas ese botón de 'reinicio', entra a nuestra web, agenda tu cita. Permítete una hora donde la única responsabilidad sea respirar y sentirte bien.</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/man-facial-and-head-massage-at-spa-for-break-ski-2025-04-06-09-56-12-utc.jpg?raw=true",
                "category": "Bienestar",
                "tags": [
                    "Masaje ansiedad Cali",
                    "Estrés y dolor muscular",
                    "Salud Mental",
                    "Cortisol",
                    "Studio Zens",
                    "Relajación profunda"
                ],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 5,
                "meta_title": "Masaje y Ansiedad: Mitos y Verdades | Studio Zens Cali",
                "meta_description": "Descubre cómo un masaje reduce el cortisol y ayuda con la ansiedad en Studio Zens Cali. Diferencias con terapia psicológica. Agenda tu paz hoy.",
                "custom_seo_keywords": "masaje antiestres cali, beneficios masaje ansiedad, spa relajante la cascada, masaje craneofacial estres, studio zens opiniones"
            },
            {
                "title": "Primer masaje profesional: qué esperar antes, durante y después de tu sesión",
                "slug": "primer-masaje-profesional-guia-cali",
                "subtitle": "¿Es tu primera vez en un spa? Deja los nervios en la puerta, aquí te contamos paso a paso cómo funciona para que solo te preocupes por relajarte.",
                "excerpt": "Es normal sentir curiosidad o timidez si nunca te has hecho un masaje. Te explicamos el protocolo de privacidad, qué ropa usar y cómo preparamos tu experiencia en Studio Zens.",
                "content": "<h2>¿Nerviosa por tu primera vez? Es totalmente normal</h2><p>Tomar la decisión de agendar tu primer masaje es el paso más difícil. A menudo nos preguntamos: <em>'¿Qué ropa me quito?', '¿Me va a doler?', '¿Será incómodo?'</em>. En <strong>Studio Zens</strong>, en el Barrio La Cascada, recibimos a muchas personas que se estrenan en el mundo del bienestar, y nuestra prioridad es que te sientas segura y en confianza desde el minuto uno.</p><h2>Antes de la sesión: La preparación</h2><p>No necesitas traer nada especial. Nosotros proveemos toallas, sábanas limpias y aceites de primera calidad.</p><ul><li><strong>Llegada:</strong> Te recomendamos llegar unos 10 minutos antes. Esto te permite bajar las revoluciones del tráfico de Cali y usar el baño si lo necesitas.</li><li><strong>Comunicación:</strong> Al llegar, cuéntale a tu terapeuta si tienes alguna zona dolorida o si, por el contrario, prefieres que no toquen cierta área (como los pies o el abdomen).</li></ul><h2>Durante el masaje: Tu privacidad es sagrada</h2><p>Esta es la duda número uno. En un masaje profesional (como nuestra <strong>Experiencia Zen</strong> o el <strong>Terapéutico</strong>):</p><ul><li><strong>La ropa:</strong> Te quedarás en ropa interior. Si lo prefieres, te daremos una toalla para cubrirte.</li><li><strong>La técnica de la toalla (Draping):</strong> Nunca estarás expuesta. Nuestros terapeutas están entrenados para destapar <strong>únicamente</strong> la parte del cuerpo que están trabajando (por ejemplo, la espalda o una pierna) mientras el resto de tu cuerpo permanece calientito y cubierto bajo la sábana. El respeto es absoluto.</li></ul><h2>Después de la sesión: El regreso a la tierra</h2><p>Al terminar, no te levantaremos de golpe. Te daremos unos minutos para que despiertes poco a poco. Es posible que sientas mucha sed o ganas de orinar; es normal, tu cuerpo está movilizando toxinas. Bebe mucha agua el resto del día.</p><p><em>¡Ya viste que no hay nada que temer! Si estás lista para tu debut en el mundo del relax, visita nuestra web y reserva tu primera cita. Te prometemos que querrás repetir.</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/happy-female-friends-drinking-lemonade-at-health-s-2025-01-23-02-28-54-utc.jpg?raw=true",
                "category": "Bienestar",
                "tags": ["Primer masaje", "Protocolo Spa", "Studio Zens", "Dudas frecuentes", "Relax Cali"],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 4,
                "meta_title": "Mi Primer Masaje en Cali: Guía Principiantes | Studio Zens",
                "meta_description": "¿Primera vez en un spa? Te explicamos el protocolo de ropa, privacidad y qué esperar en tu primer masaje relajante en Studio Zens Cali.",
                "custom_seo_keywords": "que ropa llevar a un masaje, protocolo masaje relajante cali, es doloroso el masaje terapeutico, spa para principiantes cali"
            },
            {
                "title": "Cuidados de la piel después de un facial: errores comunes que debes evitar",
                "slug": "cuidados-despues-facial-errores-comunes",
                "subtitle": "Acabas de invertir en tu rostro, ¡no lo arruines al salir! Consejos para que el efecto 'glow' te dure semanas.",
                "excerpt": "Salir de una Hidra-limpieza y exponerse al sol de Cali sin protección es un error clásico. Aprende qué hacer (y qué no) en las 24 horas siguientes a tu facial.",
                "content": "<h2>Ese brillo post-facial es oro puro</h2><p>Acabas de salir de <strong>Studio Zens</strong> después de una <strong>Limpieza Facial Profunda</strong> o una <strong>Hidra-limpieza</strong>. Tu piel respira, se siente suavecita y tienes un brillo natural envidiable. Pero, ¡ojo! Las próximas 24 a 48 horas son críticas. Tus poros están limpios pero también más expuestos, y cometer ciertos errores puede irritar tu piel o desperdiciar el tratamiento.</p><h2>Error #1: Maquillarte inmediatamente</h2><p>Sabemos que quieres verte divina, pero intenta (por favor) no aplicar bases pesadas ni polvos justo al salir. Tu piel está absorbiendo los nutrientes que le aplicamos. Si le pones maquillaje encima, es como tapar los poros que acabamos de limpiar.</p><h2>Error #2: Subestimar el sol de Cali</h2><p>Incluso si está nublado o ya son las 4:00 PM, la radiación UV es el enemigo. Después de una exfoliación o microdermoabrasión (parte de nuestros procesos de limpieza), tu piel es nueva y sensible. El bloqueador solar no es negociable; es tu escudo. Si sales de nuestra sede en La Cascada, intenta no caminar mucho bajo el sol directo.</p><h2>Error #3: Tocar tu cara (o dejar que otros la toquen)</h2><p>Evita tocarte el rostro con las manos sucias o dejar que tu pareja te apapache la cara justo después. Las bacterias de las manos pueden causar brotes en esos poros que están tan receptivos.</p><h2>Error #4: Exfoliarte en casa</h2><p>¡No lo hagas! Nosotros ya hicimos el trabajo pesado de remover células muertas. Si usas scrubs o ácidos en casa al día siguiente, solo lograrás irritar y poner roja tu piel.</p><h2>Lo que SÍ debes hacer</h2><p>Hidratarte mucho (beber agua), cambiar la funda de tu almohada esa noche por una limpia y usar tus cremas hidratantes suaves.</p><p><em>¿Lista para renovar tu piel de la manera correcta? Agenda tu facial en nuestra web y déjanos cuidarte como te mereces.</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/a-breathtaking-and-stunning-portrait-depicting-an-2025-12-05-16-12-27-utc.jpg?raw=true",
                "category": "Spa",
                "tags": ["Cuidado facial", "Post tratamiento", "Errores belleza", "Protección solar", "Studio Zens"],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 3,
                "meta_title": "Cuidados Post Limpieza Facial Cali | Tips Studio Zens",
                "meta_description": "¿Qué no hacer después de un facial? Evita el sol, maquillaje y exfoliantes. Guía de cuidados post-facial para mantener tu piel radiante en Cali.",
                "custom_seo_keywords": "puedo maquillarme despues de una limpieza facial, cuidados post peeling cali, sol despues de facial, hidratacion post limpieza"
            },
            {
                "title": "Masajes para personas que trabajan sentadas: cuello, espalda y postura",
                "slug": "masajes-para-trabajo-oficina-sedentarismo",
                "subtitle": "¿Tu oficina es tu enemiga? Si pasas más de 6 horas frente al computador, tu espalda baja y tu cuello te están pidiendo auxilio.",
                "excerpt": "El 'cuello de texto' y el dolor lumbar son las dolencias más comunes del teletrabajo. Descubre cómo el Masaje Terapéutico Focalizado puede salvar tu postura.",
                "content": "<h2>El mal del siglo XXI: La silla de oficina</h2><p>Ya sea que trabajes desde casa (Home Office) o en una oficina en el norte o sur de Cali, la historia es la misma: hombros encogidos hacia las orejas, cuello adelantado mirando la pantalla y una presión constante en la zona lumbar. A esto le llamamos 'postura de oficina', y a largo plazo, no solo causa dolor, sino que baja tu energía y productividad.</p><h2>¿Por qué duele tanto?</h2><p>Estar sentada reduce la circulación en las piernas y carga todo el peso del torso en la espalda baja. Además, el estrés de las fechas de entrega hace que, inconscientemente, tensemos los trapecios (esos músculos entre el cuello y el hombro).</p><h2>La solución en Studio Zens: Terapéutico Focalizado</h2><p>Para este problema específico, no siempre necesitas un masaje de cuerpo completo. En nuestro menú de servicios <strong>Integrales</strong>, diseñamos el <strong>Terapéutico Focalizado I</strong>.</p><ul><li><strong>¿Qué hacemos?</strong> Nos concentramos 100% en la zona del problema (generalmente espalda alta, cuello y hombros).</li><li><strong>La técnica:</strong> Usamos presión firme para liberar los 'puntos gatillo' (esos nudos duros que sientes al tocarte).</li><li><strong>El resultado:</strong> Sientes que el cuello te crece un par de centímetros y que la 'mochila' desaparece.</li></ul><h2>Prevención y Mantenimiento</h2><p>Además de visitarnos regularmente para 'resetear' tu postura, te recomendamos:</p><ul><li>Ajustar la altura de tu monitor (que quede a nivel de tus ojos).</li><li>Levantarte cada hora, aunque sea para ir por agua.</li><li>Agendar un <strong>Terapéutico Mixto</strong> si sientes que el estrés mental es tan alto como el físico.</li></ul><h2>Tu pausa activa está en La Cascada</h2><p>Estamos ubicados estratégicamente para que puedas venir después del trabajo o un sábado en la mañana. Contamos con estacionamiento para que no sumes estrés buscando dónde parquear.</p><p><em>No normalices vivir con dolor de espalda. Entra a nuestra web, busca la categoría 'Integrales' y regálate el alivio que tu cuerpo trabajador merece.</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/overworked-frustrated-indian-businessman-manager-2025-03-08-23-03-07-utc.jpg?raw=true",
                "category": "Integrales",
                "tags": ["Dolor de espalda", "Ergonomía", "Masaje Terapéutico", "Home Office Cali", "Salud laboral", "Studio Zens"],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": False,
                "reading_time_minutes": 4,
                "meta_title": "Masajes para Dolor de Espalda Oficina Cali | Studio Zens",
                "meta_description": "¿Trabajas sentado todo el día? Alivia el dolor de cuello y espalda baja con nuestros masajes terapéuticos focalizados en Cali. Mejora tu postura hoy.",
                "custom_seo_keywords": "dolor lumbar por estar sentado, masaje cuello y hombros cali, tratamiento para torticolis, masaje descontracturante espalda"
            },
            {
                "title": "Cómo elegir un buen centro de masajes en Cali: señales de calidad y confianza",
                "slug": "elegir-buen-spa-masajes-cali-confianza",
                "subtitle": "No dejes tu cuerpo en manos de cualquiera. Te enseñamos a identificar un lugar profesional, seguro y de alta calidad.",
                "excerpt": "La oferta en Cali es enorme, pero no todos los sitios ofrecen higiene, profesionalismo y respeto. Aprende las 'Green Flags' (señales buenas) que definen a un spa serio como Studio Zens.",
                "content": "<h2>Tu cuerpo es un templo, cuídalo</h2><p>En Cali hay muchísimos lugares que ofrecen masajes, pero cuando se trata de tu salud y tu intimidad, no puedes tomar riesgos. Elegir un spa no es solo buscar 'el precio más bajo', es buscar seguridad, higiene y técnica profesional. Como expertas en bienestar, queremos darte los tips para que identifiques un lugar de calidad (¡y por qué nosotras nos esforzamos tanto en cumplirlo!).</p><h2>1. Transparencia en la información (La Web)</h2><p>Un sitio serio no tiene miedo de mostrar sus precios y servicios. Si tienes que enviar mil mensajes para que te den un valor, desconfía. En <strong>Studio Zens</strong>, nuestra web de agendamiento muestra claramente qué incluye cada servicio, cuánto dura y cuánto cuesta. Sin sorpresas ni costos ocultos.</p><h2>2. Higiene impecable</h2><p>Desde que entras, el lugar debe oler a limpio, no a humedad. Las sábanas y toallas deben cambiarse rigurosamente con cada cliente. Nosotros contamos con duchas privadas y protocolos de limpieza estrictos porque tu salud es lo primero.</p><h2>3. Profesionalismo y Respeto (La regla de oro)</h2><p>Este es el punto más importante. Un centro de masajes terapéutico y de relajación tiene límites claros.</p><ul><li><strong>Uniforme y actitud:</strong> El personal debe estar debidamente uniformado y mantener una actitud 100% profesional.</li><li><strong>Cero ambigüedades:</strong> Un spa serio se enfoca en salud y bienestar. Si el lugar ofrece cosas que suenan 'extrañas' o fuera de lo terapéutico, huye. En Studio Zens somos tajantes: nuestros servicios son estrictamente profesionales, enfocados en tu relajación muscular y mental.</li></ul><h2>4. Ubicación y Seguridad</h2><p>Busca lugares en zonas tranquilas y seguras. Nuestra sede en el <strong>Barrio La Cascada</strong> (Carrera 64) fue elegida pensando en ti: un entorno residencial, tranquilo y con estacionamiento privado para clientes, para que tu experiencia de relax empiece desde que te bajas del carro.</p><h2>5. Reseñas y recomendaciones</h2><p>Lo que dicen otros clientes importa. Un buen servicio al cliente, puntualidad en las citas y amabilidad son sellos de garantía.</p><p><em>Ahora que sabes qué buscar, te invitamos a comprobar por qué somos la opción de confianza para tantas personas en Cali. Visita nuestra web, conoce nuestros protocolos y agenda tu cita con total tranquilidad.</em></p>",
                "image_url": "https://github.com/BillyJoe121/Studio-zens-notifications-images/blob/main/blog%20SEO%20images/spa-essentials-with-white-towels-plumeria-flowers-2025-10-12-16-36-39-utc.jpg?raw=true",
                "category": "Bienestar",
                "tags": ["Seguridad Spa", "Mejores masajes Cali", "Consejos bienestar", "Studio Zens", "Calidad y servicio"],
                "author_name": "Equipo Studio Zens",
                "status": "published",
                "is_featured": True,
                "reading_time_minutes": 5,
                "meta_title": "Cómo Elegir el Mejor Spa en Cali: Guía | Studio Zens",
                "meta_description": "Consejos para elegir un centro de masajes seguro y profesional. Higiene, precios claros y respeto. Descubre por qué Studio Zens es tu opción confiable.",
                "custom_seo_keywords": "masajes seguros cali, spa recomendado cali, precios masajes cali, sitio de masajes serio, spa barrio la cascada"
            }
        ]

        # 1. Crear categorías y etiquetas
        self.stdout.write(self.style.WARNING('Creando categorías y etiquetas...'))
        
        # Extraer categorías y etiquetas únicas
        categories_names = set(art['category'] for art in articles_data)
        tags_names = set()
        for art in articles_data:
            for tag in art['tags']:
                tags_names.add(tag)

        # Crear categorías
        for cat_name in categories_names:
            Category.objects.get_or_create(
                name=cat_name,
                defaults={'description': f'Artículos sobre {cat_name}'}
            )
            self.stdout.write(f'✓ Categoría: {cat_name}')

        # Crear etiquetas
        for tag_name in tags_names:
            Tag.objects.get_or_create(name=tag_name)
        self.stdout.write(f'✓ {len(tags_names)} Etiquetas creadas')

        # 2. Crear artículos
        self.stdout.write(self.style.WARNING('Creando artículos...'))

        for i, art_data in enumerate(articles_data):
            # Obtener categoría
            category = Category.objects.get(name=art_data['category'])
            
            # Obtener etiquetas
            tags = Tag.objects.filter(name__in=art_data['tags'])

            # Fecha de publicación escalonada
            days_ago = len(articles_data) - i
            published_date = timezone.now() - timedelta(days=days_ago)

            article, created = Article.objects.get_or_create(
                slug=art_data['slug'],
                defaults={
                    'title': art_data['title'],
                    'subtitle': art_data['subtitle'],
                    'excerpt': art_data['excerpt'],
                    'content': art_data['content'],
                    'category': category,
                    'status': art_data.get('status', 'published'),
                    'published_at': published_date,
                    'is_featured': art_data.get('is_featured', False),
                    'author_name': art_data.get('author_name', 'Equipo Studio Zens'),
                    'reading_time_minutes': art_data.get('reading_time_minutes', 5),
                    'meta_title': art_data.get('meta_title', ''),
                    'meta_description': art_data.get('meta_description', ''),
                    'views_count': random.randint(100, 1000),
                }
            )
            
            # Descargar imagen si existe
            if 'image_url' in art_data:
                try:
                    self.stdout.write(f"Descargando imagen para {article.slug}...")
                    response = requests.get(art_data['image_url'])
                    if response.status_code == 200:
                        # Extraer nombre del archivo de la URL
                        # Usamos slug + extensión jpg para simplificar ya que algunas urls no tienen extension clara o son largas
                        file_name = f"{article.slug}.jpg"
                        article.cover_image.save(file_name, ContentFile(response.content), save=True)
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Imagen descargada: {file_name}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"  ✗ Error {response.status_code} al descargar imagen"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ✗ Excepción al descargar imagen: {str(e)}"))

            if not created:
                # Si ya existe, actualizamos los campos clave
                article.title = art_data['title']
                article.subtitle = art_data['subtitle']
                article.content = art_data['content']
                article.excerpt = art_data['excerpt']
                article.category = category
                article.status = art_data.get('status', 'published')
                article.is_featured = art_data.get('is_featured', False)
                article.reading_time_minutes = art_data.get('reading_time_minutes', 5)
                article.meta_title = art_data.get('meta_title', '')
                article.meta_description = art_data.get('meta_description', '')
                article.save()

            article.tags.set(tags)
            self.stdout.write(self.style.SUCCESS(f'✓ Artículo creado/actualizado: {article.title}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Blog poblado exitosamente con artículos definitivos!'))
