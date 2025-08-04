# -- coding: utf-8 --
# ==============================================================================
# --- Parte 1: Módulos necesarios ---
# ==============================================================================

from aqt import mw
from aqt.qt import (QAction, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                    QLineEdit, QPushButton, QFileDialog, QProgressBar, QLabel,
                    pyqtSignal, QObject, QRunnable, QThreadPool, pyqtSlot,
                    Qt, QGroupBox, QWidget, QMenu)
from aqt.utils import showInfo, qconnect
import webbrowser
import os
import sys

# --- Configuración del Add-on ---
# Esto añade la carpeta 'vendor' al path de Python para que pueda encontrar las librerías.
addon_path = os.path.dirname(__file__)
vendor_path = os.path.join(addon_path, "vendor")
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

# Ahora estas importaciones deberían funcionar directamente desde la carpeta vendor
import pysrt
import pandas as pd
import spacy
import re
from collections import Counter
import base64
import numpy as np
from langdetect import detect, LangDetectException

# ==============================================================================
# --- Parte 2: TRABAJADORES (Análisis y Procesamiento) ---
# ==============================================================================

class AnalysisWorker(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

    def __init__(self, input_path):
        super(AnalysisWorker, self).__init__()
        self.signals = self.Signals()
        self.input_path = input_path
        self.is_cancelled = False
        
        self.MODEL_NAME = "en_core_web_sm" 
        self.VOCAB_CSV_FILE = os.path.join(addon_path, "user_files", 'vocabulario.csv')
        self.PHRASAL_VERBS_FILE = os.path.join(addon_path, "user_files", 'phrasal_verbs.csv')
        self.EASY_WORDS_FILE = os.path.join(addon_path, "user_files", 'EasyWords.txt')
        
        self.DIFFICULTY_PERCENTILE = 90
        self.CEFR_ORDER = {'a1': 1, 'a2': 2, 'b1': 3, 'b2': 4, 'c1': 5, 'c2': 6}
        self.CEFR_REVERSE_MAP = {v: k for k, v in self.CEFR_ORDER.items()}
        
    def get_level_value(self, level_str): return self.CEFR_ORDER.get(str(level_str).lower(), 0)
    def load_vocab_db(self, filepath):
        df = pd.read_csv(filepath, engine='python', encoding='utf-8-sig'); df.columns = [c.strip().lower() for c in df.columns]
        return {str(r['word']).lower(): {'core': str(r['core_level']).lower(), 'advanced': str(r['advanced_level']).lower()} for _, r in df.iterrows()}
    def load_phrasal_verbs_db(self, filepath, nlp):
        df, phrases = pd.read_csv(filepath), []
        for _, r in df.iterrows(): phrases.append({'text': str(r['phrase']).lower(), 'level': str(r['level']), 'lemmas': [t.lemma_ for t in nlp(str(r['phrase']).lower())]})
        phrases.sort(key=lambda x: len(x['lemmas']), reverse=True); return phrases
    def load_easy_words(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f: return {l.strip().lower() for l in f if l.strip()}
    def analyze_line(self, text, base_level_val, nlp, vocab_db, phrasal_verbs_db, easy_words):
        doc = nlp(re.sub(r'<[^>]+>', '', re.sub(r'\(\((.*?)\)\)', r'\1', text))); difficult_items, max_level_val, processed_tokens = [], 0, [False] * len(doc)
        for p in phrasal_verbs_db:
            p_lemmas, p_len = p['lemmas'], len(p['lemmas'])
            for i in range(len(doc) - p_len + 1):
                if processed_tokens[i]: continue
                if [t.lemma_ for t in doc[i:i+p_len]] == p_lemmas:
                    phrase_text, level_val = doc[i:i+p_len].text.strip(), self.get_level_value(p['level'])
                    if level_val > base_level_val: difficult_items.append(phrase_text)
                    max_level_val = max(max_level_val, level_val); [processed_tokens.__setitem__(j, True) for j in range(i, i + p_len)]
        for i, t in enumerate(doc):
            if not processed_tokens[i] and not t.is_punct and not t.is_space and t.lemma_.lower() not in easy_words:
                try:
                    if detect(t.lemma_) != 'en': continue
                except LangDetectException: pass
                word_levels = vocab_db.get(t.lemma_.lower())
                if word_levels:
                    core_val, adv_val = self.get_level_value(word_levels.get('core','a1')), self.get_level_value(word_levels.get('advanced','a1'))
                    if core_val > base_level_val: difficult_items.append(t.text.strip())
                    max_level_val = max(max_level_val, adv_val)
                else: max_level_val = max(max_level_val, self.get_level_value('a1'))
        return max_level_val, list(dict.fromkeys(difficult_items))

    @pyqtSlot()
    def run(self):
        try:
            if self.is_cancelled: return
            
            # --- VERSIÓN FINAL: Carga directa del modelo ---
            # Asumimos que todo lo necesario está en la carpeta 'vendor'.
            try:
                nlp = spacy.load(self.MODEL_NAME)
            except OSError:
                self.signals.error.emit(f"Error Crítico: El modelo '{self.MODEL_NAME}' no se encontró en la carpeta 'vendor' del addon. El addon puede estar corrupto o mal instalado. Por favor, contacta al autor.")
                return

            vocab_db = self.load_vocab_db(self.VOCAB_CSV_FILE)
            phrasal_verbs_db = self.load_phrasal_verbs_db(self.PHRASAL_VERBS_FILE, nlp)
            easy_words = self.load_easy_words(self.EASY_WORDS_FILE)
            subs = pysrt.open(self.input_path, encoding='utf-8')
            all_levels = [self.analyze_line(s.text, 0, nlp, vocab_db, phrasal_verbs_db, easy_words)[0] for s in subs]
            difficult_levels = [l for l in all_levels if l > self.get_level_value('a2')]
            if difficult_levels:
                video_difficulty_level = int(round(np.percentile(difficult_levels, self.DIFFICULTY_PERCENTILE)))
            elif all_levels:
                video_difficulty_level = Counter(all_levels).most_common(1)[0][0]
            else:
                video_difficulty_level = self.get_level_value('a1')
            
            base_level_val = max(1, video_difficulty_level - 1)
            base_level_str = self.CEFR_REVERSE_MAP.get(base_level_val, "N/A").upper()

            results = {"level": base_level_str, "total_lines": len(subs)}
            self.signals.finished.emit(results)
        except Exception as e:
            self.signals.error.emit(f"Error durante el análisis: {e}")

class ProcessingWorker(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(str)
        error = pyqtSignal(str)
        progress = pyqtSignal(int)
        status = pyqtSignal(str)
        
    def __init__(self, input_paths, output_folder):
        super(ProcessingWorker, self).__init__()
        self.signals = self.Signals()
        self.input_paths = input_paths
        self.output_folder = output_folder
        self.is_cancelled = False
        
        self.MODEL_NAME = "en_core_web_sm"
        self.VOCAB_CSV_FILE = os.path.join(addon_path, "user_files", 'vocabulario.csv')
        self.PHRASAL_VERBS_FILE = os.path.join(addon_path, "user_files", 'phrasal_verbs.csv')
        self.EASY_WORDS_FILE = os.path.join(addon_path, "user_files", 'EasyWords.txt')

        self.DIFFICULTY_PERCENTILE = 90
        self.MAX_SILENCE_MS = 1500
        self.MAX_CHARS_PER_SUB = 800
        self.CEFR_ORDER = {'a1': 1, 'a2': 2, 'b1': 3, 'b2': 4, 'c1': 5, 'c2': 6}

    # ... (Todos los métodos de ayuda como get_level_value, load_vocab_db, etc., se quedan igual) ...
    def get_level_value(self, level_str): return self.CEFR_ORDER.get(str(level_str).lower(), 0)
    def load_vocab_db(self, filepath):
        df = pd.read_csv(filepath, engine='python', encoding='utf-8-sig'); df.columns = [c.strip().lower() for c in df.columns]
        return {str(r['word']).lower(): {'core': str(r['core_level']).lower(), 'advanced': str(r['advanced_level']).lower()} for _, r in df.iterrows()}
    def load_phrasal_verbs_db(self, filepath, nlp):
        df, phrases = pd.read_csv(filepath), []
        for _, r in df.iterrows(): phrases.append({'text': str(r['phrase']).lower(), 'level': str(r['level']), 'lemmas': [t.lemma_ for t in nlp(str(r['phrase']).lower())]})
        phrases.sort(key=lambda x: len(x['lemmas']), reverse=True); return phrases
    def load_easy_words(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f: return {l.strip().lower() for l in f if l.strip()}
    def analyze_line(self, text, base_level_val, nlp, vocab_db, phrasal_verbs_db, easy_words):
        doc = nlp(re.sub(r'<[^>]+>', '', re.sub(r'\(\((.*?)\)\)', r'\1', text))); difficult_items, max_level_val, processed_tokens = [], 0, [False] * len(doc)
        for p in phrasal_verbs_db:
            p_lemmas, p_len = p['lemmas'], len(p['lemmas'])
            for i in range(len(doc) - p_len + 1):
                if processed_tokens[i]: continue
                if [t.lemma_ for t in doc[i:i+p_len]] == p_lemmas:
                    phrase_text, level_val = doc[i:i+p_len].text.strip(), self.get_level_value(p['level'])
                    if level_val > base_level_val: difficult_items.append(phrase_text)
                    max_level_val = max(max_level_val, level_val); [processed_tokens.__setitem__(j, True) for j in range(i, i + p_len)]
        for i, t in enumerate(doc):
            if not processed_tokens[i] and not t.is_punct and not t.is_space and t.lemma_.lower() not in easy_words:
                try:
                    if detect(t.lemma_) != 'en': continue
                except LangDetectException: pass
                word_levels = vocab_db.get(t.lemma_.lower())
                if word_levels:
                    core_val, adv_val = self.get_level_value(word_levels.get('core','a1')), self.get_level_value(word_levels.get('advanced','a1'))
                    if core_val > base_level_val: difficult_items.append(t.text.strip())
                    max_level_val = max(max_level_val, adv_val)
                else: max_level_val = max(max_level_val, self.get_level_value('a1'))
        return max_level_val, list(dict.fromkeys(difficult_items))
    def highlight_difficult_items(self, text, difficult_items):
        for item in sorted(difficult_items, key=len, reverse=True): text = re.sub(r'\b' + re.escape(item) + r'\b', f"(({item}))", text, flags=re.IGNORECASE)
        return text
    def merge_interactive_subs(self, sub_buffer):
        if not sub_buffer: return None
        s_vis, s_data, s_times, start_time = [], [], [], sub_buffer[0].start.ordinal
        for s in sub_buffer:
            clean = s.text.strip().replace('\n', ' '); s_vis.append(clean); s_data.append(base64.b64encode(clean.encode('utf-8')).decode('utf-8')); s_times.append(str(s.start.ordinal - start_time))
        data_island = f"<!--DATA|{'|'.join(s_data)}##{','.join(s_times)}-->"
        return pysrt.SubRipItem(0, sub_buffer[0].start, sub_buffer[-1].end, " ".join(s_vis) + data_island)

    @pyqtSlot()
    def run(self):
        try:
            self.signals.status.emit("Cargando modelo de IA (spaCy)..."); self.signals.progress.emit(0)
            if self.is_cancelled: return
            
            # --- VERSIÓN FINAL: Carga directa del modelo ---
            try:
                nlp = spacy.load(self.MODEL_NAME)
            except OSError:
                self.signals.error.emit(f"Error Crítico: El modelo '{self.MODEL_NAME}' no se encontró en la carpeta 'vendor' del addon. El addon puede estar corrupto o mal instalado. Por favor, contacta al autor.")
                return

            self.signals.status.emit("Cargando base de datos de vocabulario..."); self.signals.progress.emit(20)
            if self.is_cancelled: return
            vocab_db = self.load_vocab_db(self.VOCAB_CSV_FILE)
            self.signals.status.emit("Cargando base de datos de Phrasal Verbs..."); self.signals.progress.emit(25)
            if self.is_cancelled: return
            phrasal_verbs_db = self.load_phrasal_verbs_db(self.PHRASAL_VERBS_FILE, nlp)
            self.signals.status.emit("Cargando lista de palabras fáciles..."); self.signals.progress.emit(30)
            if self.is_cancelled: return
            easy_words = self.load_easy_words(self.EASY_WORDS_FILE)
            PROGRESS_START = 35; PROGRESS_RANGE = 100 - PROGRESS_START
            for i, input_path in enumerate(self.input_paths):
                if self.is_cancelled: return
                file_name = os.path.basename(input_path)
                self.signals.status.emit(f"Procesando archivo: {file_name}")
                subs = pysrt.open(input_path, encoding='utf-8'); total_subs = len(subs)
                all_levels = [self.analyze_line(s.text, 0, nlp, vocab_db, phrasal_verbs_db, easy_words)[0] for s in subs]
                difficult_levels = [l for l in all_levels if l > self.get_level_value('a2')]
                video_difficulty_level = int(round(np.percentile(difficult_levels, self.DIFFICULTY_PERCENTILE))) if difficult_levels else (Counter(all_levels).most_common(1)[0][0] if all_levels else self.get_level_value('a1'))
                base_level_val = max(1, video_difficulty_level - 1); final_subs, easy_line_buffer = [], []
                for j, sub in enumerate(subs):
                    if self.is_cancelled: return
                    self.signals.progress.emit(PROGRESS_START + int(((j + 1) / total_subs) * PROGRESS_RANGE))
                    _, difficult_items = self.analyze_line(sub.text, base_level_val, nlp, vocab_db, phrasal_verbs_db, easy_words)
                    sub.text = self.highlight_difficult_items(sub.text, difficult_items)
                    if len(difficult_items) > 0:
                        context_sub = easy_line_buffer.pop() if easy_line_buffer else None
                        if easy_line_buffer: final_subs.append(self.merge_interactive_subs(easy_line_buffer)); easy_line_buffer = []
                        if context_sub: final_subs.append(pysrt.SubRipItem(0, context_sub.start, sub.end, context_sub.text + " " + sub.text))
                        else: final_subs.append(sub)
                    else:
                        if not easy_line_buffer: easy_line_buffer.append(sub)
                        else:
                            last_sub, b_len = easy_line_buffer[-1], len(" ".join(s.text for s in easy_line_buffer))
                            if (sub.start.ordinal - last_sub.end.ordinal) > self.MAX_SILENCE_MS or (b_len + len(sub.text) + 1) > self.MAX_CHARS_PER_SUB:
                                final_subs.append(self.merge_interactive_subs(easy_line_buffer)); easy_line_buffer = [sub]
                            else: easy_line_buffer.append(sub)
                if easy_line_buffer: final_subs.append(self.merge_interactive_subs(easy_line_buffer))
                for idx, sub_item in enumerate(final_subs, 1):
                    if sub_item: sub_item.index = idx
                final_srt = pysrt.SubRipFile(items=[s for s in final_subs if s is not None])
                final_srt.save(os.path.join(self.output_folder, f"mine2anki_{file_name}"), encoding='utf-8')
            if not self.is_cancelled: self.signals.finished.emit("¡Proceso completado! Archivo guardado.")
        except Exception as e:
            self.signals.error.emit(f"Error en {os.path.basename(self.input_paths[-1])}: {e}")

# ==============================================================================
# --- Parte 3: INTERFAZ GRÁFICA (Sin cambios) ---
# ==============================================================================
class ProgressDialog(QDialog):
    def __init__(self, title="Procesando...", parent=None):
        super().__init__(parent); self.setWindowTitle(title); self.setModal(True); self.setMinimumWidth(450); self.finished = False
        self.progress_bar = QProgressBar(); self.status_label = QLabel("Iniciando..."); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cancel_button = QPushButton("Cancelar"); layout = QVBoxLayout()
        layout.addWidget(self.status_label); layout.addWidget(self.progress_bar); layout.addWidget(self.cancel_button); self.setLayout(layout)
    def closeEvent(self, event):
        if not self.finished: self.cancel_button.click()
        else: event.accept()
class WaitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Analizando"); self.setModal(True)
        layout = QVBoxLayout(); self.label = QLabel("Analizando, por favor espere..."); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label); self.setLayout(layout)
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Acerca de Mine2Anki")
        VERSION = "1.5"; AUTOR = "co1000"; CONTACTO = "codecks1000@gmail.com"; WEBSITE_URL = "https://github.com/co1000" # Subí la versión
        ACKNOWLEDGEMENTS = """<p>Este add-on fue inspirado por la funcionalidad y el flujo de trabajo de herramientas
        clásicas de la comunidad de aprendizaje de idiomas, especialmente <b>subs2srs</b>.</p>
        <p>Utiliza las siguientes librerías de código abierto:</p>
        <ul><li><b>spaCy</b> para el procesamiento de lenguaje natural.</li><li><b>Pandas</b> para la gestión de datos.</li>
        <li><b>PySRT</b> para la manipulación de subtítulos.</li><li><b>Langdetect</b> para la detección de idiomas.</li></ul>"""
        layout = QVBoxLayout()
        title = QLabel(f'<h2>Mine2Anki</h2><p>Versión {VERSION}</p>'); title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        form_layout = QFormLayout(); form_layout.addRow("<b>Autor:</b>", QLabel(AUTOR)); form_layout.addRow("<b>Contacto:</b>", QLabel(CONTACTO))
        website_label = QLabel(f'<a href="{WEBSITE_URL}">{WEBSITE_URL}</a>'); website_label.setOpenExternalLinks(True)
        form_layout.addRow("<b>Sitio Web:</b>", website_label); layout.addLayout(form_layout)
        ack_box = QGroupBox("Info"); ack_layout = QVBoxLayout()
        ack_label = QLabel(ACKNOWLEDGEMENTS); ack_label.setWordWrap(True); ack_label.setTextFormat(Qt.TextFormat.RichText)
        ack_layout.addWidget(ack_label); ack_box.setLayout(ack_layout); layout.addWidget(ack_box); self.setLayout(layout)
class MainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Optimizar Subtítulos"); self.setMinimumSize(600, 400)
        self.create_single_srt_page(); self.create_output_groupbox(); self.create_action_buttons()
        main_layout = QVBoxLayout(); main_layout.addWidget(self.input_groupbox); main_layout.addWidget(self.results_groupbox)
        main_layout.addStretch(); main_layout.addWidget(self.output_groupbox); main_layout.addLayout(self.action_buttons_layout)
        self.setLayout(main_layout); self.threadpool = QThreadPool(); self.load_config()
    def create_single_srt_page(self):
        self.input_groupbox = QGroupBox("Archivo de Entrada"); form_layout = QFormLayout()
        self.single_input_path = QLineEdit(); self.browse_single_button = QPushButton("Buscar...")
        input_row = QHBoxLayout(); input_row.addWidget(self.single_input_path); input_row.addWidget(self.browse_single_button)
        form_layout.addRow("Archivo .srt:", input_row); self.input_groupbox.setLayout(form_layout)
        self.results_groupbox = QGroupBox("Resultado del Análisis"); results_layout = QFormLayout()
        self.level_label = QLabel(); self.lines_label = QLabel()
        results_layout.addRow("<b>Nivel Base para Resaltar:</b>", self.level_label)
        results_layout.addRow("Líneas de Subtítulo:", self.lines_label)
        self.results_groupbox.setLayout(results_layout); self.results_groupbox.setVisible(False)
        self.browse_single_button.clicked.connect(self.on_browse_single_file)
        self.single_input_path.textChanged.connect(lambda: self.results_groupbox.setVisible(False))
    def create_output_groupbox(self):
        self.output_groupbox = QGroupBox("Opciones de Salida"); layout = QFormLayout()
        self.output_path_edit = QLineEdit(); self.browse_output_button = QPushButton("Buscar...")
        output_row = QHBoxLayout(); output_row.addWidget(self.output_path_edit); output_row.addWidget(self.browse_output_button)
        layout.addRow("Guardar archivo en:", output_row); self.output_groupbox.setLayout(layout)
        self.browse_output_button.clicked.connect(self.on_browse_output_folder)
    def create_action_buttons(self):
        self.action_buttons_layout = QHBoxLayout(); self.help_button = QPushButton("Ayuda")
        help_menu = QMenu(self); USAGE_URL = "https://telegra.ph/Metodología-de-Creación-del-Mazo-08-03-2"
        help_menu.addAction("Uso", lambda: webbrowser.open(USAGE_URL)); help_menu.addAction("Acerca de...", self.show_about_dialog)
        self.help_button.setMenu(help_menu); self.action_buttons_layout.addWidget(self.help_button); self.action_buttons_layout.addStretch()
        self.analyze_button = QPushButton("Analizar..."); self.generate_button = QPushButton("¡Optimizar!")
        self.generate_button.setStyleSheet("font-weight: bold;")
        self.action_buttons_layout.addWidget(self.analyze_button); self.action_buttons_layout.addWidget(self.generate_button)
        self.analyze_button.clicked.connect(self.on_analyze); self.generate_button.clicked.connect(self.on_start_generation)
    def show_about_dialog(self): dialog = AboutDialog(self); dialog.exec()
    def load_config(self): self.output_path_edit.setText(mw.col.conf.get('mine2anki_last_output_path', os.path.join(os.path.expanduser("~"), "Desktop")))
    def save_config(self):
        mw.col.conf['mine2anki_last_output_path'] = self.output_path_edit.text()
        last_input = ""
        if self.single_input_path.text(): last_input = os.path.dirname(self.single_input_path.text())
        if last_input: mw.col.conf['mine2anki_last_input_path'] = last_input
        mw.col.flush()
    def on_browse_single_file(self):
        last_path = mw.col.conf.get('mine2anki_last_input_path', os.path.expanduser("~"))
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleccionar Archivo SRT", last_path, "*.srt")
        if filepath: self.single_input_path.setText(filepath)
    def on_analyze(self):
        path_to_analyze = self.single_input_path.text()
        if not path_to_analyze: showInfo("Por favor, selecciona un archivo .srt para analizar."); return
        self.set_ui_enabled(False); self.wait_dialog = WaitDialog(self)
        self.analysis_worker = AnalysisWorker(path_to_analyze)
        self.analysis_worker.signals.finished.connect(self.on_analysis_finished)
        self.analysis_worker.signals.error.connect(self.on_processing_error)
        self.threadpool.start(self.analysis_worker); self.wait_dialog.exec()
    def on_analysis_finished(self, results):
        self.wait_dialog.close(); self.set_ui_enabled(True)
        self.level_label.setText(f"<b>{results['level']}</b>"); self.lines_label.setText(str(results['total_lines']))
        self.results_groupbox.setVisible(True)
    def on_browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", self.output_path_edit.text())
        if folder: self.output_path_edit.setText(folder)
    def on_start_generation(self):
        output_folder = self.output_path_edit.text()
        if not os.path.isdir(output_folder): showInfo("Por favor, selecciona una carpeta de salida válida."); return
        input_path = self.single_input_path.text()
        if not input_path: showInfo("No hay archivo para procesar."); return
        self.save_config(); self.set_ui_enabled(False)
        self.progress_dialog = ProgressDialog("Optimizando...", self)
        self.processing_worker = ProcessingWorker([input_path], output_folder)
        self.processing_worker.signals.progress.connect(self.progress_dialog.progress_bar.setValue)
        self.processing_worker.signals.status.connect(self.progress_dialog.status_label.setText)
        self.processing_worker.signals.finished.connect(self.on_processing_finished)
        self.processing_worker.signals.error.connect(self.on_processing_error)
        def on_cancel(): self.processing_worker.is_cancelled = True; self.progress_dialog.finished = True; self.progress_dialog.close()
        self.progress_dialog.cancel_button.clicked.connect(on_cancel)
        self.threadpool.start(self.processing_worker); self.progress_dialog.exec(); self.set_ui_enabled(True)
    def on_processing_finished(self, final_message):
        self.progress_dialog.finished = True
        self.progress_dialog.close()
        showInfo(final_message)
        self.single_input_path.clear()
        self.results_groupbox.setVisible(False)
    def on_processing_error(self, error_message):
        if hasattr(self, 'wait_dialog') and self.wait_dialog.isVisible(): self.wait_dialog.close()
        if hasattr(self, 'progress_dialog') and self.progress_dialog.isVisible(): self.progress_dialog.finished = True; self.progress_dialog.close()
        self.set_ui_enabled(True); showInfo(f"Ocurrió un error:\n\n{error_message}")
    def set_ui_enabled(self, enabled):
        self.input_groupbox.setEnabled(enabled); self.output_groupbox.setEnabled(enabled)
        self.analyze_button.setEnabled(enabled); self.generate_button.setEnabled(enabled); self.help_button.setEnabled(enabled)
    def closeEvent(self, event):
        self.threadpool.clear(); self.threadpool.waitForDone(-1); event.accept()

# ==============================================================================
# --- Parte 4: Integración final con el Menú de Anki ---
# ==============================================================================
def show_main_dialog():
    if not hasattr(mw, 'mine2anki_dialog') or not mw.mine2anki_dialog.isVisible():
        mw.mine2anki_dialog = MainDialog(mw)
        mw.mine2anki_dialog.show()
    else:
        mw.mine2anki_dialog.activateWindow()

action = QAction("Optimizar Subtítulos", mw)
qconnect(action.triggered, show_main_dialog)
mw.form.menuTools.addAction(action)