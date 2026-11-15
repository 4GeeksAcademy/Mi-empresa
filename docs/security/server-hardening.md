# Endurecimiento de servidor — baseline y procedimiento recomendado

**Actualizado:** 2026-11-15. Este documento distingue la evidencia local del repositorio de resultados del VPS compartidos por el operador/agente autorizado. Las IPs, hostname, claves y secretos se omiten. La evidencia del VPS no fue obtenida directamente desde este entorno y se registra como salida comunicada por el operador; no es un pentest ni una certificación.

## Baseline conocido

- El repositorio incluye aplicaciones FastAPI/Next.js y servicios auxiliares; sus puertos de desarrollo no definen qué debe publicarse en producción.
- El requisito TrackFlow es público: HTTPS para API/frontend; SSH solo para operaciones. No publicar Redis, Qdrant, Flower, bases de datos ni puertos de desarrollo al exterior.
- El VPS comunicado es Ubuntu 22.04.5 LTS. `trackflowops` tiene UID/GID 1000, acceso SSH por clave y pertenece al grupo `sudo`.
- Se informó que `PermitRootLogin no`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no` y `PubkeyAuthentication yes` fueron comprobados con `sshd -T` antes y después de recargar `ssh.service`; `sshd -t` pasó.
- Se informó que UFW está activo con entrada denegada por defecto, salida permitida y una única regla entrante TCP 22 restringida al origen de la sesión de configuración. `IPV6=yes`.
- Se informó una conexión nueva satisfactoria como `trackflowops` después de activar UFW y una prueba externa de SSH como `root` que devolvió `Permission denied (publickey)`.
- La regla de UFW está limitada al origen observado durante la configuración; no se ha demostrado que ese origen sea una IP administrativa estable. Las reglas del firewall del proveedor siguen sin verificarse.
- Compose de desarrollo publica `6379`, `6333/6334` y `5555`, además de frontend/API según variables; no se comprobó bind address ni firewall externo. No trasladar esa publicación sin cambios a producción.
- Flower declara API no autenticada. Mantenerlo deshabilitado o accesible solo en red administrativa autenticada/protegida; su puerto no debe quedar público.

## Objetivo mínimo

1. Crear una cuenta nominal operativa sin privilegios globales; elevar privilegios solo mediante `sudo` auditado, con MFA/llaves según política organizacional.
2. Validar acceso de la cuenta nueva en una sesión independiente antes de impedir root. Configurar `PermitRootLogin no`, `PasswordAuthentication no` si se dispone de llaves probadas, `AllowUsers <cuenta-operativa>` (o grupo autorizado), y recargar `sshd` tras `sshd -t`. Mantener consola/rollback fuera de banda.
3. Separar propietarios/permisos: código de solo lectura para el usuario de runtime (`root:app`, directorios 0750 y archivos 0640 como política inicial); configuración y secretos accesibles únicamente por root/servicio (`root:app`, directorios 0750/secretos 0640 o más restrictivos); logs escribibles solo por servicio y grupo de operación (0750/0640), con rotación y retención. Ajustar a necesidades reales; no aplicar recursivamente sin inventario.
4. Firewall por defecto deny inbound. Permitir 443/TCP al proxy/API/frontend y SSH (22/TCP u otro puerto acordado) solo desde VPN/bastion/rangos de operaciones. Abrir 80 solo si se requiere redirección/certificado ACME. Egress mínimo necesario; bloquear Redis, Qdrant, Flower y puertos internos desde Internet.
5. TLS vigente, parches del SO, actualizaciones controladas, copias de seguridad, sincronización de tiempo, monitoreo de SSH y política de incidentes.

## Verificación segura en host autorizado

Ejecutar primero en modo lectura, guardar salida saneada y no imprimir claves privadas/secretos:

```sh
id
getent passwd <cuenta-operativa>
sudo sshd -T | grep -E '^(permitrootlogin|passwordauthentication|allowusers)'
sudo sshd -t
sudo stat -c '%U:%G %a %n' /ruta/app /ruta/config /ruta/logs
sudo ufw status verbose                 # si se usa UFW
sudo nft list ruleset                   # alternativa si se usa nftables
sudo ss -lntup
```

Confirmar desde otra sesión la autenticación operativa y que root no puede abrir una sesión SSH, antes de cerrar la sesión de mantenimiento. Validar el firewall desde una máquina externa autorizada: solo HTTPS y SSH desde el origen permitido; los servicios internos deben fallar al conectarse desde fuera. Revisar también reglas del proveedor cloud, balanceador y firewall del contenedor: el firewall del host no demuestra por sí solo la exposición efectiva.

## Evidencia saneada del VPS (2026-11-15)

**Fuente y límite:** resultados pegados por el operador desde PowerShell y resúmenes de auditoría del agente del VPS. No se incluye la IP pública, hostname, passphrase, contraseña ni contenido de claves. No se afirma verificación independiente desde este repositorio.

| Control | Comprobación / evidencia comunicada | Evaluación |
|---|---|---|
| SSH de root | `sshd -T` comunicó `permitrootlogin no`; prueba externa con `BatchMode=yes`, clave pública y contraseña deshabilitada respondió `Permission denied (publickey)`. | Cubierto con configuración efectiva reportada y prueba negativa externa. |
| SSH por contraseña | `sshd -T` comunicó `passwordauthentication no`; también `kbdinteractiveauthentication no` y `pubkeyauthentication yes`. `sshd -t` pasó antes y después de recargar el servicio. | Cubierto según salidas comunicadas; no se conserva IP ni transcripción íntegra. |
| Cuenta operativa | Inicio nuevo por clave como `trackflowops`; `whoami` devolvió `trackflowops`. `sudo -v` se completó correctamente desde sesión interactiva. | Cubierto para acceso y elevación sudo. El usuario operativo tiene privilegios administrativos vía sudo, no es una cuenta de mínimo privilegio absoluto. |
| Directorios operativos | Se informó que `/opt/trackflow`, `/var/lib/trackflow` y `/var/log/trackflow` pertenecen a `trackflowops:trackflowops` con modo `750`. | Cubierto para estas rutas según auditoría comunicada. La aplicación aún no está desplegada; no se ha verificado un usuario runtime separado ni permisos de ficheros de aplicación/secretos. |
| Firewall local | El agente comunicó: estado UFW activo; `deny incoming`, `allow outgoing`; única regla de entrada `22/tcp ALLOW IN` desde el origen observado; sin reglas de aplicación; `IPV6=yes`. | Cubierto según salida resumida del agente; conservar el informe original localmente si se requiere evidencia íntegra. |
| Conectividad posterior a UFW | Desde una ventana nueva de PowerShell se estableció sesión SSH por clave como `trackflowops`; `sudo -v` fue aceptado. | Cubierto mediante salida pegada por el operador. |
| Puertos/listeners | El agente comunicó SSH TCP 22 en todas las interfaces; listeners restantes observados en loopback; no se abrieron 80/443 ni puertos de aplicación. | Revisión básica cubierta según estado comunicado. No equivale a escaneo externo del VPS. |
| Firewall del proveedor | No hay acceso/confirmación del panel de la academia. | No verificado; control externo separado de UFW. |

### Revalidación SSH/UFW desde Windows (2026-11-15)

- En el VPS, `sudo sshd -T` volvió a mostrar `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no` y `pubkeyauthentication yes`.
- Desde Windows se hizo un intento con `PubkeyAuthentication=no` y solo métodos `password,keyboard-interactive`; SSH llegó al servidor, anunció que solo podía continuar con `publickey` y terminó en `Permission denied (publickey)` sin pedir contraseña de cuenta. Esto verifica externamente el rechazo de autenticación por contraseña en el momento de la prueba.
- `sudo ufw status numbered` y `sudo ufw status verbose` mostraron UFW activo, `deny (incoming)`, `allow (outgoing)` y una sola regla entrante TCP 22 permitida desde una única dirección de origen; no se conserva la dirección en este documento.
- El operador comparó el origen de la regla con la IP de salida observada desde PowerShell y confirmó que coinciden. La dirección concreta se omite. Esto confirma la red actual, no que la IP sea estática o vaya a seguir siendo la habitual.
- Se omite deliberadamente la huella de host que apareció en el log verbose: no es necesaria para evidenciar este control.

La evidencia demuestra controles locales en el VPS en la fecha indicada, según resultados comunicados. No confirma que el firewall de red del proveedor filtre tráfico, que la IP permitida sea estable, ni que los puertos sean inaccesibles desde todas las redes externas.

## Evaluación de los criterios de la tarea

1. **SSH directo como root deshabilitado:** cubierto por `sshd -T` comunicado y rechazo externo de SSH.
2. **Usuario operativo no-root y permisos explícitos:** cubierto parcialmente. Se verificaron login por clave, sudo y modos/propietarios de tres directorios. `trackflowops` pertenece a `sudo`; el servicio de aplicación aún no está desplegado y no se verificó una identidad runtime separada. Esto sí satisface la existencia de un usuario operativo no-root, pero no demuestra mínimo privilegio ni separación operativa/runtime completa.
3. **Firewall con exposición mínima:** firewall local cubierto según `ufw status` comunicado: entrada por defecto denegada, salida permitida, solo SSH desde el origen observado. Firewall del proveedor no verificado. Sin aplicación desplegada, no se justifican puertos web todavía.
4. **OWASP Top 10:** evaluación estática explícita de las diez categorías documentada en [`owasp-top10-audit.md`](./owasp-top10-audit.md). No es pentest ni evidencia de despliegue.
5. **Sistema agéntico como componente propio:** carril agente/RAG/MCP separado en la auditoría OWASP. Parcial: se ejecutaron cuatro patrones offline y un smoke live de tres casos sintéticos contra el endpoint/modelo aprobado, con cero indicadores heurísticos; esto no es red-team amplio ni prueba de robustez. Siguen pendientes el aislamiento multi-tenant/B2B/B2C (si aplica) y la prueba live MCP→API con credencial de servicio provisionada.
6. **Vulnerabilidades críticas corregidas con antes/después:** cubierto para las dependencias de UI auditadas: se documentaron los advisories críticos previos y auditorías posteriores con cero críticas. No cubre host, imágenes o componentes fuera de esos lockfiles; permanecen advisories no críticos.

## Pendiente / mantenimiento

- Pedir a la academia confirmación del firewall del proveedor y conservarla sin publicar direcciones.
- Cuando se despliegue la aplicación, definir puertos necesarios a partir de la arquitectura y repetir `ufw status verbose`, `ss -tulpn` y una verificación externa autorizada. No exponer Redis, Qdrant, Flower ni puertos internos.
- Revisar si la regla SSH restringida sigue correspondiendo a la IP administrativa habitual; actualizarla con acceso de recuperación disponible si cambia la red.
- Guardar la evidencia original en un lugar privado de entrega si se necesita auditoría formal; este documento conserva solo síntesis redactadas.
- La configuración del servidor no se modificó desde este workspace. Los cambios de SSH/UFW descritos fueron realizados por el agente/operador en el VPS.
