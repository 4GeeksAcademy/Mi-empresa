# `uis` folder

This folder contains **all the user interfaces** related to the company for the cross-functional AI Engineering project (for example: web applications, internal dashboards, customer portals, Streamlit/Gradio apps, etc.).

Each subfolder inside `uis/` must correspond to **one specific user interface** (for example: `website`, `backoffice`) and include its own technical and functional documentation.

- **Main purpose**: to centralize in a single place all the frontend applications that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the applications you add, their objective, the technology used, and how to run them.

> _Spanish version: [README.es.md](./README.es.md)._

## Desarrollo con Docker

El entorno completo se inicia desde la raiz con `docker compose up`. El contenedor
`interfaces` ejecuta `website` en el puerto 3000 y `backoffice` en el 3001, ambos
con recarga en caliente. Las aplicaciones usan el servicio `backend` para sus
peticiones internas; no deben configurarse URLs `localhost` entre contenedores.
