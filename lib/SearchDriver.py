import sys, os

import ssl
import selenium
from selenium import webdriver
from bs4 import BeautifulSoup

lUserAgent = [
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
]
nPos = 0

def getUA():
  global nPos
  nPos = (nPos + 1) % len(lUserAgent)
  return lUserAgent[nPos]

class SearchDriver(webdriver.Chrome):
  def __init__ (self):
    initialize()
    self.options = webdriver.ChromeOptions()
    self.service = webdriver.ChromeService(executable_path=chromeDriver)
    
    # headless options
    self.options.add_argument('headless')
    self.options.add_argument('window-size=1920x1080')
    if sys.platform == 'linux':
      self.options.add_argument('no-sandbox') # Error in Windows
      self.options.add_argument('disable-dev-shm-usage')
    self.options.add_argument('disable-gpu')
    self.options.add_argument('lang=ko_KR')
    
    # humanlike options
    self.options.add_argument('user-agent='+getUA())
    self.options.add_argument("disable-blink-features=AutomationControlled")
    self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
    self.options.add_experimental_option('useAutomationExtension', False)
    
    # delogging
    if sys.platform == 'win32':
      self.service.creation_flags = 0x08000000 # no console log from selenium to stderr
    self.options.add_argument('disable-logging')
    self.options.add_argument("disable-in-process-stack-traces")
    # self.options.add_argument('log-level=2')
    self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # disable download & caching
    self.options.add_experimental_option("prefs", {
      "download.default_directory": os.devnull
      })
    self.options.add_argument("disable-cache")
    
    # ignore ssl, certificate
    self.options.add_argument('ignore-certificate-errors')
    self.options.add_argument('ignore-ssl-errors')
    self.options.add_argument('allow-insecure-localhost')
    self.options.add_argument('disable-web-security')
    self.options.add_argument('allow-insecure-localhost')
    self.options.add_argument('ignore-urlfetcher-cert-requests')
    self.options.accept_insecure_certs = True
    ssl._create_default_https_context = ssl._create_unverified_context
    
    super().__init__(service=self.service, options=self.options)
    self.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
  
  def __del__ (self):
    self.quit()


initialized = False
chromeDriver = None
def initialize():
  global initialized, chromeDriver
  if not initialized:
    # chromeDriver = ChromeDriverManager().install()
    initialized = True

if __name__ == "__main__":
  crawler = SearchDriver()
  crawler.quit()
  a = getattr(crawler.service, 'is_connectable', lambda:False)
  print(a)
  crawler.quit()