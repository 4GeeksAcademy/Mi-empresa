# Diseño del chat WebSocket de TrackFlow

Contrato consultado: `sistemas-en-tiempo-real-2-BRIEFING.es.md` (raíz). El agente sigue siendo `first_line_cx`; cada `ChatSession` usa `session_id`, `user_id`, `client_id`, `status` y `created_at`. El mismo `session_id` es `thread_id` de LangGraph.

## Transporte y contrato

Se usa WebSocket porque no solo se transmiten tokens servidor→cliente: el usuario debe enviar una redirección mientras el stream sigue vivo y que esta cancele la generación en curso. SSE solo resuelve el primer sentido. El socket autentica con el JWT existente `?token=` antes de aceptar mensajes. Eventos de aplicación siguen exclusivamente el briefing: `session_snapshot`, `user_message`, `token_chunk`, `interrupt_requested`, `generation_interrupted` y `generation_completed`; no se reutilizan eventos RFP/SSE.

El frontend persiste el `session_id` en localStorage, reabre el WebSocket con backoff exponencial acotado y reemplaza su estado local con `session_snapshot` (mensajes completos, tokens parciales y estado). El backend guarda sesiones e historial en `agent.sqlite3`, el almacén privado persistente actual del agente, para rehidratar si se reinicia el proceso.

## Producción y consumidores

`ChatHub` es productor/consumidor pub/sub en memoria, un canal lógico por sesión. Una sola ejecución agente genera y publica cada chunk una vez; todas las colas WebSocket suscritas reciben el mismo evento. Añadir un supervisor no vuelve a llamar al agente. La generación corre en un pool; el hub guarda mensaje parcial y estado y desacopla los sockets de la llamada a LangGraph. El mecanismo en memoria es single-process según lo permitido por el briefing; varias réplicas necesitan un backplane durable/compartido.

## Cancelación y turnos

Los chunks del OpenAI-compatible provider se consumen con `stream=True`. El sink es local a la invocación mediante `ContextVar`; el evento de cancelación `threading.Event` detiene iteración y se registra `response.close()` para cerrar el stream al recibir interrupción. No se usa LangGraph HITL `interrupt()`: aquí no hay pausa reanudable de aprobación, sino cancelación del proveedor y fin del turno actual. La interrupción marca el mensaje parcial `interrupted`, no lo elimina. El servidor espera al productor cancelado antes de reutilizar el mismo `thread_id`; luego guarda el nuevo mensaje de usuario y ejecuta un turno independiente. La secuencia se conserva para auditoría visual.

## Verificación

Pruebas automatizadas en `services/api/tests/test_chat.py` cubren rechazo del handshake no autenticado, orden/forma de chunks, evento terminal y restauración de historial al reconectar. El escenario de cancelación usa un productor determinista: verifica el callback de abort, conserva el chunk parcial, descarta un chunk ya almacenado al cancelar, emite el evento de interrupción y completa un nuevo turno con un `generation_id` distinto. UI tiene prueba Jest para token incremental y envío de redirección. Si se ejecuta manual: abrir `/chat`, enviar consulta, durante el stream enviar la redirección y recargar o reconectar; verificar parcial interrumpido, respuesta del nuevo turno y snapshot recuperado.

**Riesgo conocido:** el token JWT en query string es necesario para navegadores, pero URLs pueden aparecer en logs del servidor/proxy. No se registran explícitamente; producción debe además redactar query `token` y restringir el transporte a `wss://`.
