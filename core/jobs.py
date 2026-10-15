"""Tarayıcı oturumundan bağımsız tek iş yöneticisi. Streamlit çağrısı yapmaz."""
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import threading

from core.cancellation import Cancelled, checkpoint, current_cancel


@dataclass
class Job:
    owner: str
    source: Path
    temporary: Path | None
    name: str
    cancel: threading.Event = field(default_factory=threading.Event)
    status: str = 'running'
    message: str = 'Başlıyor…'
    fraction: float = 0.0
    result: object = None


class JobManager:
    def __init__(self, runner=None, saver=None):
        self.guard = threading.RLock()
        self.active = None
        self.jobs = {}
        self.model = None
        self.runner = runner or self.process
        self.saver = saver or self.save

    def submit(self, owner, source, temporary=None, name=''):
        with self.guard:
            if self.active is not None:
                return False
            # Tamamlanan işler yalnızca küçük durum bilgisi tutar.
            if len(self.jobs) >= 20:
                self.jobs.pop(next(iter(self.jobs)))
            job = Job(owner, source, temporary, name)
            self.jobs[owner] = self.active = job
            try:
                threading.Thread(target=self.run, args=(job,), daemon=True).start()
            except Exception:
                self.active = None
                self.jobs.pop(owner, None)
                raise
            return True

    def snapshot(self, owner):
        with self.guard:
            job = self.jobs.get(owner)
            return (None if job is None else {
                'status': job.status, 'message': job.message, 'fraction': job.fraction, 'result': job.result,
            }), self.active is not None

    def cancel_job(self, owner):
        with self.guard:
            job = self.active
            if job is None or job.owner != owner or job.status not in ('running', 'cancelling'):
                return False
            job.cancel.set()
            job.status = 'cancelling'
            job.message = 'İptal bekleniyor; çalışan OCR/model çağrısı bitince duracak.'
            return True

    def run(self, job):
        token = current_cancel.set(job.cancel)
        status, message = 'failed', 'Belge işlenemedi. Dosyayı kontrol edin.'
        try:
            def report(message, fraction):
                checkpoint()
                with self.guard:
                    if not job.cancel.is_set():
                        job.message, job.fraction = message, fraction
            result = self.runner(job.source, report)
            # İptal ve kayıt aynı kilidi kullanır: iptal kabul edildiyse kayıt yok.
            with self.guard:
                checkpoint()
                job.status = 'saving'
                self.saver(result, job.name)
                job.result = result
                status, message = 'done', 'İşlem tamamlandı. Sonuç Kayıtlı belgeler bölümüne kaydedildi.'
        except Cancelled:
            status, message = 'cancelled', 'İşlem iptal edildi; yarım sonuç kaydedilmedi.'
        except Exception:
            if job.cancel.is_set():
                status, message = 'cancelled', 'İşlem iptal edildi; yarım sonuç kaydedilmedi.'
        finally:
            try:
                if job.temporary is not None:
                    shutil.rmtree(job.temporary)
            except OSError:
                message += ' Geçici dosyalar temizlenemedi; uygulama sahibine bildirin.'
            finally:
                current_cancel.reset(token)
                with self.guard:
                    job.status, job.message = status, message
                    self.active = None

    def process(self, source, report):
        from core.pipeline import read_pages, extract
        from core.summarize import LocalModel
        pages = read_pages(source, on_progress=report)
        checkpoint()
        if self.model is None:
            report('Model hazırlanıyor…', .55)
            self.model = LocalModel().__enter__()
        checkpoint()
        return extract(source, pages, model=self.model, on_progress=report)

    @staticmethod
    def save(result, name):
        from core import store
        with store.session() as db:
            store.save(db, ad=name.strip() or result.name, kaynak=result.source,
                       page_texts=[(p.number, p.source, p.text) for p in result.pages],
                       ozet=result.kunye.ozet,
                       adlar={'yer':result.kunye.yer_adlari, 'sahis':result.kunye.sahis_adlari,
                              'kurum':result.kunye.kurum_adlari})
