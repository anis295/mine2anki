# mine2anki

Este add-on analiza todo el vocabulario de un archivo, determina un nivel de dificultad apropiado y resalta automáticamente todas las palabras y frases que están por encima de tu nivel, preparándolas para el programa [subs2srs](http://subs2srs.sourceforge.net/) y el add-on [movies2anki](https://ankiweb.net/shared/info/939347702).

Su objetivo es optimizar tus archivos de subtítulos (`.srt`) **antes** de que los proceses con esas herramientas. En lugar de minar frases al azar, este add-on analiza todo el vocabulario, determina un nivel de dificultad para el contenido, y resalta automáticamente las palabras y frases que son genuinamente nuevas para ti. De esta forma, cuando uses `subs2srs` o `movies2anki`, ya tendrás el trabajo difícil hecho: saber qué frases vale la pena estudiar.

---

### Requisito Indispensable: Plantilla de Tarjeta

Este add-on requiere un tipo de nota específico con una plantilla diseñada para mostrar las tarjetas de minado y de contexto correctamente.

**Instrucciones de configuración:**

1.  En Anki, ve a `Herramientas > Manejar tipos de nota > Añadir`. Selecciona `Añadir: Básico` y dale un nombre, por ejemplo, `Mine2Anki Template`.
2.  Selecciona el nuevo tipo de nota y haz clic en `Tarjetas...`.
3.  Copia y pega el contenido de los siguientes archivos en las pestañas correspondientes:

    *   **Anverso:** Copia el código de [**front.html**](./anki_template/front.html)
    *   **Reverso:** Copia el código de [**back.html**](./anki_template/back.html)
    *   **Estilo:** Copia el código de [**styling.css**](./anki_template/styling.css)

4.  Guarda los cambios. ¡Ya estás listo para usar el add-on!

---

### Tipos de Tarjetas Generadas

El proceso produce dos tipos de tarjetas optimizadas para diferentes objetivos de estudio:

*   **Tarjetas de Minado (Aislamiento de Dificultad):** Se crea una tarjeta específica cuando una línea de diálogo contiene una palabra que cumple con el criterio de minado. La palabra objetivo se resalta automáticamente, a menudo con la línea anterior como contexto. Ideales para el estudio enfocado.
*   **Tarjetas de Contexto (Agrupación Inteligente):** Las líneas de diálogo que no activan el criterio de minado se fusionan en una única tarjeta interactiva. Permiten navegar entre diálogos con video sincronizado, perfectas para la práctica de *listening* y la consolidación del contexto.

---

### Lógica del Minado: El Método de la "Regla de Oro"

A diferencia del minado tradicional, este sistema no busca simplemente palabras "difíciles", sino que utiliza una lógica de clasificación para identificar vocabulario genuinamente nuevo para el estudiante.

#### 1. La Base de Datos: `core_level` vs. `advanced_level`

El sistema se basa en una base de datos que combina las listas de [Oxford 3000/5000](https://www.oxfordlearnersdictionaries.com/wordlists/oxford-3000-5000) con 30,000 palabras de la [lista de frecuencias COCA](https://www.wordfrequency.info/intro.asp). Cada palabra tiene dos niveles de dificultad asignados:

*   **`core_level` (Nivel Básico):** El significado más común de una palabra. (Ej: *shape* como "forma" - A2).
*   **`advanced_level` (Nivel Avanzado):** Usos más complejos o idiomáticos. (Ej: *to shape an opinion* - B2).

#### 2. El Proceso del Add-on: Aplicando la "Regla de Oro"

El add-on sigue un proceso automático para decidir qué minar:

1.  **Paso 1: Detectar Nivel de Contenido.** Analiza el `advanced_level` de todas las palabras de la película para definir su dificultad general (ej: la película *Coco* es calificada como B2).
2.  **Paso 2: Establecer Nivel Objetivo.** Define el nivel de aprendizaje del estudiante un escalón por debajo (para un contenido B2, el objetivo es B1).
3.  **Paso 3: Aplicar la "Regla de Oro".** El add-on solo resalta una palabra si su `core_level` es **superior** al nivel objetivo del estudiante.

> **Ejemplo práctico:** En "Coco" (contenido B2, nivel objetivo del estudiante B1), aparece la palabra "spirit". Su `core_level` (significado "espíritu") es A2. Como A2 **no** es superior a B1, no se mina. Pero si apareciera la palabra "seize" (`core_level` B2), sí se minaría, porque B2 **es** superior a B1.

Este método se centra en vocabulario verdaderamente nuevo y evita la repetición de palabras cuyo significado básico ya conoces.

---

### Fuentes Adicionales

La clasificación también se apoya en:

*   **Verbos Frasales:** Una base de datos de *phrasal verbs* de un proyecto de código abierto.
*   **Lista de Exclusión (EasyWords.txt):** Contiene todas las palabras de los mazos de Refold: "[RefoldIngles-milv2.0.0](https://refold.la/es/store/vocabulario-fundamental-para-aprender-ingles/)" y "[Refold English Reading v1.0.2](https://refold.la/store/decks/english/english-reading-deck/)".
