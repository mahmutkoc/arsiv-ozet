"""Erişim anahtarını sohbet veya kabuk geçmişine yazmadan yerelde saklar."""
from getpass import getpass
from core.site_link import save_token

print("GitHub hesabı: mahmutkoc1\n"
      "Fine-grained token: yalnızca mahmutkoc-site deposu\n"
      "Repository permissions > Contents: Read and write\n"
      "Anahtar yalnızca bu bilgisayarda, .demo klasöründe saklanır.\n")
token = getpass("GitHub erişim anahtarını yapıştırın (ekranda görünmez): ").strip()
if token:
    save_token(token)
    print("Kaydedildi. Arşivi Başlat bir sonraki açılışta bağlantıyı otomatik güncelleyecek.")
else:
    print("Boş anahtar kaydedilmedi.")
