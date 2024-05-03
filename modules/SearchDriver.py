import time
import sys, os
import logging

import subprocess
import selenium
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.remote_connection import LOGGER
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from bs4 import BeautifulSoup

lUserAgent = [
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36",
  "Mozilla/5.0 (Linux; Android 8.0.0; SAMSUNG-SM-G950N/KSU3CRJ1 Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/8.2 Chrome/63.0.3239.111 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134",
  "Mozilla/5.0 (iPhone; CPU iPhone OS 12_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/71.0.3578.89 Safari/605.1",
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
    # self.service = webdriver.ChromeService(executable_path=chromeDriver, 
    #                                        service_args=["--log-path=chromedriver.log"])
    
    # headless options
    self.options.add_argument('headless')
    self.options.add_argument('window-size=1920x1080')
    if sys.platform == 'linux':
      self.options.add_argument('no-sandbox') # Error in Windows
    
    # humanlike options
    # self.options.add_argument('disable-gpu')
    self.options.add_argument('lang=ko_KR')
    self.options.add_argument('user-agent='+getUA())
    
    # delogging
    if sys.platform == 'win32':
      self.service.creation_flags = 0x08000000 # no console log from selenium to stderr
    self.options.add_argument('disable-logging')
    self.options.add_argument("disable-in-process-stack-traces")
    # self.options.add_argument('log-level=2')
    self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    super().__init__(service=self.service, options=self.options)
  
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
  try:
    crawler.get("https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84%ED%82%A4:%EB%8C%80%EB%AC%B8")
  except selenium.common.exceptions.WebDriverException as e:
    if "net::ERR_CONNECTION_TIMED_OUT" in e.msg:
      sys.exit(1)
    else:
      print(str(e), file=sys.stderr)
      sys.exit(1)
  
  # print(crawler.page_source)
  # lLink = crawler.find_elements(By.TAG_NAME, "a")
  # print(lLink)
  # for link in lLink:
  #   print(link.get_attribute('href'))
  # print(crawler.page_source)
  # crawler.implicitly_wait(3)
  # crawler.get_screenshot_as_file('capture_naver.png')
  crawler.close()