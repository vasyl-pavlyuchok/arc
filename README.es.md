# ARC — Adaptive Rule Context

> Inyección inteligente de reglas para Claude Code. Carga solo lo que importa, cuando importa.

Construido por [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & [Claude](https://claude.ai) (Anthropic) — dirección humana, implementación IA, autoría compartida.

🇬🇧 [English version → README.md](README.md)

---

## El problema

Cada vez que envías un mensaje en Claude Code, tu `CLAUDE.md` (o cualquier archivo de reglas estático) carga **todo** — sin importar lo que estés haciendo en ese momento.

Con 30, 50, 100 reglas entre Docker, flujos de trabajo, proyectos activos y comportamiento general, estás quemando miles de tokens por mensaje en overhead que no es relevante para la tarea actual.

Esto es el **problema CARL**: las reglas se acumulan, todo se carga en cada mensaje, y tu ventana de contexto se llena poco a poco de reglas que ahora mismo no necesitas.

Hay un segundo problema, más silencioso, que se deriva del primero: el **context rot** (deterioro del contexto). A medida que una sesión crece, la ventana de contexto se llena y Claude empieza a descartar el contenido más antiguo para hacer hueco. Sin avisar. Sin parar. Simplemente olvida — decisiones tomadas antes, restricciones que estableciste, contexto que parecía estable. Cuanto más larga la sesión, peor: Claude se contradice, repite preguntas, ignora reglas que estaba siguiendo hace una hora.

ARC ataca el context rot en dos frentes: manteniendo el overhead de reglas bajo (para que el contexto útil dure más), y monitorizando el estado de la sesión para ajustar el comportamiento antes de que las cosas vayan mal.

## La inspiración

Anthropic ya resolvió este problema — en el propio sistema de **skills** de Claude Code.

Las skills siempre son visibles como `nombre + descripción corta`. La definición completa solo se carga cuando la skill se invoca. Tienes consciencia sin overhead.

ARC aplica exactamente el mismo patrón a tus reglas:

| Sistema de skills | ARC |
|---|---|
| `nombre + descripción corta` siempre visible | Variante `_SHORT` siempre inyectada |
| Definición completa al invocar | Dominio completo al detectar keyword |
| Tú eliges la skill por nombre | Claude hace match por palabras clave en tu prompt |

No es una invención nueva — viene directamente del diseño de Anthropic. ARC solo extiende esa lógica a tus propias reglas y flujos de trabajo.

## La solución

Las reglas se organizan en **dominios** y solo se cargan cuando aparecen palabras clave relevantes en tu prompt.

| Mensaje | Qué se carga |
|---|---|
| "¿cómo funciona este componente?" | Solo GLOBAL (resúmenes cortos) |
| "arregla el problema con docker" | GLOBAL + DOCKER (reglas completas) |
| "configura el webhook de n8n" | GLOBAL + tu dominio de workflows |
| Trabajando en `/projects/miweb/` | GLOBAL + MIWEB (detección por ruta) |

**~85–90% menos overhead de contexto** — mismo comportamiento inteligente, mucho menos coste.

---

## Cómo funciona

ARC es un conjunto de hooks de Claude Code. El principal se ejecuta antes de cada mensaje e inyecta solo lo relevante.

```
Tú envías mensaje
       ↓
arc-hook.py lee ~/.arc/manifest
       ↓
¿Qué dominios hacen match con las keywords de este prompt?
¿Qué dominios hacen match con las rutas de las tool calls recientes?
       ↓
Carga: GLOBAL (variantes SHORT) + dominios con match (reglas completas)
       ↓
Inyecta como additionalContext → Claude solo ve las reglas pertinentes
```

### Tabla de hooks

| Hook | Evento | Qué hace |
|---|---|---|
| `arc-hook.py` | UserPromptSubmit | Motor principal — match de keywords + rutas, carga de dominios, context brackets |
| `arc-suggest.py` | Stop | Analiza la sesión — sugiere keywords nuevas para prompts sin match |
| `arc-semantic.py` | UserPromptSubmit | Fallback semántico — match por significado cuando las keywords no alcanzan (opt-in) |
| `output-trimmer.py` | PostToolUse (Bash) | Recorta outputs verbosos para no desperdiciar contexto |
| `secret-scanner.py` | PreToolUse (Bash) | Bloquea commits que contengan API keys o secretos hardcodeados |

### Estructura de dominios

```
~/.arc/
├── manifest        # qué dominios existen y sus keywords
├── global          # siempre cargado (solo variantes SHORT)
├── context         # reglas por nivel de contexto (FRESH/MODERATE/DEPLETED)
├── docker          # carga cuando: docker, container, compose...
├── miproyecto      # carga cuando: keywords match O path detectado
└── sessions/       # estado por sesión (gestionado automáticamente)
```

### Formato de reglas

```ini
# ~/.arc/docker
DOCKER_RULE_1_SHORT=Proxy inverso como único punto de entrada. Nunca exponer puertos.
DOCKER_RULE_1=Usa un proxy inverso (Traefik, Nginx o Caddy) como único punto de entrada
para todo el tráfico en puertos 80 y 443. Los puertos de los contenedores nunca deben
exponerse directamente a internet — ni siquiera de forma temporal. Motivos: terminación
SSL automática, enrutamiento centralizado con logs unificados, posibilidad de añadir
middleware (auth, rate-limiting, headers) en un solo lugar, y rollback limpio sin tocar
DNS. Error frecuente a evitar: mapear puertos del host en docker-compose (ej. "8080:80")
en producción — esto bypasea el proxy y crea puntos de entrada sin control que son fáciles
de olvidar y difíciles de auditar. Si necesitas probar en local, usa la red del proxy;
nunca uses el mapeo de puertos como atajo.
```

- Variante `_SHORT`: inyectada en cada prompt (compacta, ≤15 palabras)
- Variante completa: inyectada solo cuando el dominio hace match — incluye rationale, ejemplos y casos límite

### Context Brackets

Cada sesión de Claude Code tiene una ventana de contexto finita — un espacio fijo para todo: tus mensajes, las respuestas de Claude, los outputs de herramientas y las reglas inyectadas. A medida que avanza la sesión, ese espacio se va llenando. Cuando se acaba, Claude empieza a perder el contenido más antiguo en silencio. No avisa. No para. Simplemente olvida.

ARC lee el conteo de tokens del log JSONL de la sesión y calcula cuánto espacio queda. En función de ese porcentaje, sitúa la sesión en uno de cuatro **brackets** — e inyecta un conjunto distinto de reglas de comportamiento para cada uno.

| Bracket | Restante | Qué le dice ARC a Claude |
|---|---|---|
| FRESH | 60–100% | Trabaja con normalidad. Inyección mínima, poco overhead. |
| MODERATE | 40–60% | Refuerza las decisiones clave. Resume el estado antes de empezar tareas grandes. |
| DEPLETED | 25–40% | Guarda checkpoints de todo. Prepara notas de handoff por si la sesión termina. |
| CRITICAL | <25% | Avisa al usuario. Recomienda abrir una sesión nueva antes de continuar. |

**Esta es la respuesta directa de ARC al context rot.** Sin reglas que tengan en cuenta el bracket, Claude se comporta igual tanto si la sesión tiene 5 minutos como si lleva 3 horas — incluso cuando está descartando contexto en silencio. Los brackets hacen visible el estado de salud de la sesión y cambian el comportamiento de Claude en consecuencia, para detectar el deterioro antes de perder trabajo o recibir outputs inconsistentes sin saber por qué.

### Star Commands

Escribe `*comando` al inicio de tu prompt para activar un conjunto específico de reglas para ese modo, independientemente de las keywords:

```
*dev    arregla la validación del formulario de login
*review revisa este PR antes de hacer merge
```

Los star commands mapean a conjuntos de reglas dedicados definidos en tu manifest. Útil cuando quieres forzar un contexto específico — estándares de code review, checklist de deploy, protocolo de debugging — sin depender de la detección por keyword.

### Detección por ruta

ARC inspecciona las rutas de las tool calls recientes para cargar dominios automáticamente — sin que aparezcan keywords en tu prompt.

```ini
# manifest
MYAPP_PATH=/ruta/absoluta/al/proyecto
```

Si Claude lee o edita un archivo bajo esa ruta, el dominio se carga solo.

---

## Instalación

```bash
git clone https://github.com/vasyl-pavlyuchok/arc.git
cd arc
chmod +x install.sh
./install.sh
```

El instalador auto-merge los hooks necesarios en tu `~/.claude/settings.json`. Sin edición manual de JSON. Es idempotente — puedes ejecutarlo varias veces sin duplicar nada.

Reinicia Claude Code y ARC estará activo.

> **¿No sabes cómo instalarlo?** Pásale el enlace de este repositorio a tu Claude Code y él te guiará paso a paso en todo el proceso.

---

## Herramientas CLI

ARC incluye una interfaz de línea de comandos para debug e introspección.

### `arc test` — depura el matching antes de usarlo en sesión real

```bash
arc test "quiero configurar un workflow de n8n con docker"
```

```
Prompt: "quiero configurar un workflow de n8n con docker"
Always loaded (2): ✓ GLOBAL (33 reglas), ✓ CONTEXT (19 reglas)
Matched by keyword (2):
  ✓ DOCKER  — matched: docker  (12 reglas)
  ✓ N8N     — matched: n8n, workflow  (7 reglas)
Not matched (5): COMMANDS, DASHBOARD_UI, ESTETIA, SERVIDOR, VASYLPAVLYUCHOK
```

Es la herramienta más útil al construir dominios nuevos — ves exactamente qué cargaría antes de probarlo en una sesión real.

### Otros comandos

```bash
arc status           # config activa — devmode, dominios, estado
arc domains          # lista completa con keywords y conteo de reglas
arc sessions         # últimas sesiones con título, prompt count, última actividad
arc stats            # informe de tokens ahorrados (delega a arc-stats.py)
arc stats --week     # últimos 7 días
arc stats --month    # últimos 30 días
```

Sin dependencias externas — funciona inmediatamente tras la instalación.

### `arc-stats` — mide el ahorro real

`arc-stats.py` procesa el log de output-trimmer y reporta números reales:

```
Período: últimos 7 días
Activaciones: 47
Líneas recortadas: 1,823 → 312 (83% de reducción)
Tokens estimados ahorrados: ~3,800
Top comandos: git diff (18), docker logs (12), npm install (9)
```

Convierte el "85–90% estimado" en un número real para tu uso específico.

---

## Crear tus propios dominios

**1. Crea el archivo de dominio** en `~/.arc/miproyecto`:

```ini
# ARC Domain: MIPROYECTO
MIPROYECTO_RULE_1_SHORT=Leer CLAUDE.md antes de tocar cualquier archivo del proyecto.
MIPROYECTO_RULE_1=Siempre leer el CLAUDE.md del proyecto antes de hacer cambios. Contiene
decisiones de arquitectura y restricciones que no son obvias desde el código.

MIPROYECTO_RULE_2_SHORT=Dev: docker compose -f docker-compose.dev.yml up
MIPROYECTO_RULE_2=Para desarrollo: docker compose -f docker-compose.dev.yml up
Deploy producción: docker compose build && docker compose up -d
```

**2. Regístralo en `~/.arc/manifest`**:

```ini
MIPROYECTO_STATE=active
MIPROYECTO_ALWAYS_ON=false
MIPROYECTO_RECALL=miproyecto, mi-app, feature-x, deploy staging
MIPROYECTO_PATH=/ruta/absoluta/al/proyecto   # opcional: carga automática por ruta
```

**3. Listo.** La próxima vez que menciones una keyword o trabajes en esa ruta, el dominio se carga solo.

---

## Avanzado: Matching semántico

Por defecto ARC usa keyword matching — rápido y sin overhead. Para casos donde la keyword exacta no aparece en el prompt, puedes activar el matching semántico como fallback.

```ini
# ~/.arc/manifest
SEMANTIC_MATCHING=true
SEMANTIC_THRESHOLD=0.55
```

Al activarlo:
- Solo actúa cuando el keyword matching devuelve 0 dominios con match
- Usa `sentence-transformers` con el modelo `all-MiniLM-L6-v2` (~80MB, funciona offline)
- Los embeddings se cachean en `~/.arc/embeddings.cache.pkl`
- Añade ~1–2s de latencia solo en los casos de fallback, 0ms en el resto

**Ejemplo**: "arregla el servicio que no levanta" → matchea DOCKER aunque no aparezca la palabra "docker".

> Requiere `pip install sentence-transformers`. Desactivado por defecto — el keyword matching cubre la gran mayoría de casos.

---

## Protocolo de evolución ARC

ARC está diseñado para crecer contigo. Cuando Claude detecta un patrón repetible, propone una regla:

> *"Patrón ARC detectado — dominio DOCKER, regla propuesta: 'Siempre revisar los logs del contenedor antes de asumir que un servicio está caído.' ¿La registramos?"*

Las reglas solo se añaden cuando tú confirmas. Las que resultan obsoletas se eliminan. **ARC se mantiene lean o se convierte en ruido.**

Una regla se gana su lugar solo si cumple los tres criterios:
1. **Repetible** — aplica en futuras sesiones
2. **Accionable** — cambia comportamiento concreto
3. **Estable** — no va a necesitar cambios en semanas

### arc-suggest — evolución automática

Al cerrar cada sesión, `arc-suggest.py` analiza tus prompts y propone candidatos para nuevos dominios o keywords:

```
💡 ARC: Unmatched prompts this session suggest new keywords:
   supabase  (appeared in 3 unmatched prompts)
   migration (appeared in 2 unmatched prompts)
```

No bloquea — nunca interrumpe el flujo. Solo aparece cuando hay algo que vale la pena capturar.

---

## Requisitos

- Claude Code (cualquier versión con soporte de hooks)
- Python 3.10+
- macOS, Linux o WSL
- `sentence-transformers` solo si activas el matching semántico

---

## Filosofía

Los archivos de reglas estáticos son un buen punto de partida. Pero no escalan.

ARC trata las reglas como código: organizadas por dominio, cargadas bajo demanda, evolucionando con el uso, y eliminadas cuando quedan obsoletas. El resultado es un setup de Claude Code que se vuelve más inteligente con el tiempo — sin llenar nunca la ventana de contexto. Las reglas que no se ganan su lugar se eliminan. El sistema se mantiene lean porque eso es exactamente el objetivo.

---

## Licencia

MIT — construido por [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & Claude.
