# TravelPlanner

El sistema tiene como objetivo permitir que un usuario planifique un viaje completo utilizando una plataforma web desarrollada en Python, que integra Streamlit para la capa de presentación, un backend en Flask/Django y SQLAlchemy como ORM para la interacción con la base de datos.

El usuario ingresa información básica del viaje: destino, fechas, presupuesto estimado y preferencias personales (tipo de viaje, intereses y nivel de gasto). El sistema se conecta con un modelo de IA que genera un itinerario preliminar compuesto por actividades ordenadas por día, junto con una descripción de cada una y sugerencias adicionales.

Una vez generado el itinerario, el sistema aplica una Regla de Negocio de Cálculo para estimar el costo total del viaje. Esta regla combina el precio del alojamiento, transporte, actividades diarias y gastos de comida, y luego ajusta el valor final según el tipo de viaje elegido.

La capa de negocio controla la coherencia del viaje:

Si el costo supera el presupuesto del usuario, la IA reoptimiza el itinerario para ajustarse.
Si el usuario tiene preferencias marcadas (p. ej., “naturaleza”), la IA prioriza actividades correspondientes.

La información generada se guarda en la base de datos: itinerario, actividades, costos estimados y recomendaciones IA.
El frontend desarrollado en Streamlit permite al usuario visualizar todo de manera dinámica, incluyendo gráficos de costos, tarjetas de actividades, métricas del viaje.

Arquitectura en capas:

-Capa de presentación → Streamlit
-Capa de negocio → Regla de cálculo, validaciones, optimización
-Capa de datos → ORM, modelos, consultas
-Capa de integración → IA (OpenAI/HuggingFace) + APIs externas

Entidades/Tablas:

Usuario:

Viaje:

