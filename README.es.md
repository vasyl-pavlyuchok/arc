# ARC — Adaptive Rule Context

> Inyección inteligente de reglas para Claude Code. Carga solo lo que importa.

🇬🇧 [English version → README.md](README.md)

---

## El problema

Cada vez que envías un mensaje en Claude Code, tu `CLAUDE.md` (o cualquier archivo de reglas estático) carga **todo** — sin importar lo que estés haciendo en ese momento.

Con 30, 50, 100 reglas acumuladas entre Docker, flujos de trabajo, proyectos activos y comportamiento general, estás quemando miles de tokens por mensaje en contexto que no es relevante para la tarea actual.

Esto es el **problema CARL**: las reglas se acumulan, todo se carga en cada mensaje, y tu ventana de contexto se llena poco a poco de reglas que ahora mismo no necesitas.

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

**85–90% menos overhead de contexto** — mismo comportamiento inteligente, mucho menos coste.

---

## Cómo funciona

ARC es un hook `UserPromptSubmit` de Claude Code. Se ejecuta antes de cada mensaje e inyecta solo lo relevante.

```
Tú envías mensaje
       ↓
arc-hook.py lee ~/.arc/manifest
       ↓
¿Qué dominios hacen match con las keywords de este prompt?
       ↓
Carga: GLOBAL (variantes SHORT) + dominios con match (reglas completas)
       ↓
Inyecta como additionalContext → Claude solo ve las reglas pertinentes
```

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
# domains/docker
DOCKER_RULE_1_SHORT=Proxy inverso como único punto de entrada. Nunca exponer puertos.
DOCKER_RULE_1=Usa un proxy inverso (Traefik, Nginx, Caddy) como único punto de entrada
en 80/443. Nunca expongas puertos de contenedores directamente a internet.
```

- Variante `_SHORT`: inyectada en cada prompt (compacta, ≤15 palabras)
- Variante completa: inyectada solo cuando el dominio hace match por keyword

### Context Brackets

ARC monitoriza cuánta ventana de contexto queda y ajusta el comportamiento:

| Bracket | Restante | Comportamiento |
|---|---|---|
| FRESH | 60-100% | Inyección mínima, poco overhead |
| MODERATE | 40-60% | Reforzar contexto clave, resumir antes de tareas grandes |
| DEPLETED | 25-40% | Checkpoint de todo, preparar handoffs |
| CRITICAL | <25% | Aviso y recomendación de sesión nueva |

---

## Instalación

```bash
git clone https://github.com/vasyl-pavlyuchok/arc.git
cd arc
chmod +x install.sh
./install.sh
```

Luego añade los hooks a `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/arc-hook.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/output-trimmer.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/secret-scanner.py"
          }
        ]
      }
    ]
  }
}
```

Reinicia Claude Code y ARC estará activo.

> **¿No sabes cómo instalarlo?** Pásale el enlace de este repositorio a tu Claude Code y él te guiará paso a paso en todo el proceso.

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

## Protocolo de evolución ARC

ARC está diseñado para crecer contigo. Cuando Claude detecta un patrón repetible, propone una regla:

> *"Patrón ARC detectado — dominio DOCKER, regla propuesta: 'Siempre revisar los logs del contenedor antes de asumir que un servicio está caído.' ¿La registramos?"*

Las reglas solo se añaden cuando tú confirmas. Las que resultan obsoletas se eliminan. **ARC se mantiene lean o se convierte en ruido.**

Una regla se gana su lugar solo si cumple los tres criterios:
1. **Repetible** — aplica en futuras sesiones
2. **Accionable** — cambia comportamiento concreto
3. **Estable** — no va a necesitar cambios en semanas

---

## Hooks incluidos

| Hook | Evento | Qué hace |
|---|---|---|
| `arc-hook.py` | UserPromptSubmit | Motor principal — match de keywords, carga de dominios, context brackets |
| `output-trimmer.py` | PostToolUse (Bash) | Recorta outputs verbosos (git, docker, npm) para no desperdiciar contexto |
| `secret-scanner.py` | PreToolUse (Bash) | Bloquea commits que contengan API keys o secretos hardcodeados |
| `auto-commit.sh` | Stop | Auto-checkpoint de cambios WIP al cerrar la sesión de Claude Code |

---

## Requisitos

- Claude Code (cualquier versión con soporte de hooks)
- Python 3.10+
- macOS, Linux o WSL

---

## Filosofía

Los archivos de reglas estáticos son un buen punto de partida. Pero no escalan.

ARC trata las reglas como código: organizadas por dominio, cargadas bajo demanda, evolucionando con el uso, y eliminadas cuando quedan obsoletas. El resultado es un setup de Claude Code que se vuelve más efectivo con el tiempo — sin llenar nunca la ventana de contexto.

La idea central no es nueva. Mira cómo funcionan las skills de Claude Code: la descripción corta siempre es visible, la definición completa solo carga al invocarla. Es lazy loading aplicado al contexto de IA. ARC trae ese mismo principio a tus reglas — la arquitectura ya estaba ahí, nosotros solo conectamos los puntos.

---

## Licencia

MIT — construido por [Vasyl Pavlyuchok](https://github.com/vasyl-pavlyuchok) & Claude.
