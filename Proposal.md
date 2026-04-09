# TravelPlanner

El sistema tiene como objetivo permitir que un usuario planifique un viaje completo utilizando una plataforma web desarrollada en Python, que integra Streamlit para la capa de presentación, un backend en Flask/Django y SQLAlchemy como ORM para la interacción con la base de datos.

El usuario ingresa información básica del viaje: destino, fechas, presupuesto estimado y preferencias personales (tipo de viaje, intereses y nivel de gasto). El sistema se conecta con un modelo de IA que genera un itinerario preliminar compuesto por actividades ordenadas por día, junto con una descripción de cada una y sugerencias adicionales. Se generarán 3 viajes, variando el presupuesto inicial, para dar distintas opciones al usuario, quién podrá elegir el viaje que mas le guste.

Una vez generado el itinerario, el sistema aplica una Regla de Negocio de Cálculo para estimar el costo total del viaje. Esta regla combina el precio del alojamiento, transporte, actividades diarias y gastos de comida, y luego ajusta el valor final según el tipo de viaje elegido.

La capa de negocio controla la coherencia del viaje:

Si el costo supera el presupuesto del usuario, la IA reoptimiza el itinerario para ajustarse.
Si el usuario tiene preferencias marcadas (p. ej., “naturaleza”), la IA prioriza actividades correspondientes.

La información generada se guarda en la base de datos: itinerario, actividades, costos estimados y recomendaciones IA.
El frontend desarrollado en Streamlit permite al usuario visualizar todo de manera dinámica, incluyendo gráficos de costos, tarjetas de actividades, métricas del viaje.


##Arquitectura en capas:

-Capa de presentación → Streamlit <br>
-Capa de negocio → Regla de cálculo, validaciones, optimización <br>
-Capa de datos → ORM, modelos, consultas <br>
-Capa de integración → IA (OpenAI/HuggingFace) + APIs externas <br>


##Entidades/Tablas:

###Usuario:<br>
-id_usuario<br>
-nombre<br>
-email<br>
-nacionalidad<br>
-fecha_registro<br>

###Viaje:<br>
-idViaje<br>
-destino<br>
-fechaInicio<br>
-fechaFin<br>
-tipoViaje<br>
-/costoTotalEstimado<br>

###Itinerario:<br>
-idIntinerario<br>
-dia<br>
-resumenDiaIA<br>

###Actividad:<br>
-idActividad<br>
-nombre<br>
-descripcion<br>
-precioEstimado<br>
-categoria<br>
-horarioSugerido<br>
-ubicacion<br>


###Costos:<br>
-costoAlojamiento<br>
-costoTransporte<br>
-costoActividades<br>
-costoComidas<br>
-costoTotalBase<br>

###PreferenciasUsuario:<br>
-destino<br>
-costoMin<br>
-costoMax<br>
-cantidadPersonas<br>
-grupo<br>
-clima<br>
-otros<br>

###tipoAlojamiento:<br>
-idTipo<br>
-tipo<br>

###RecomendacionIA:<br>
-textoGenerado<br>
-fechaGeneracion<br>
-tipo<br>

