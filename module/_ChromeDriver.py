import time
import sys, os

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

class _ChromeDriver(webdriver.Chrome):
  def __init__ (self):
    self.options = webdriver.ChromeOptions()
    self.service = webdriver.ChromeService(executable_path=chromeDriver)
        
    # headless options
    self.options.add_argument('headless')
    # self.options.add_argument('no-sandbox') # Error in Windows
    
    # humanlike options
    # self.options.add_argument('disable-gpu')
    # self.options.add_argument('lang=ko_KR')
    self.options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36')
    super().__init__(service=self.service, options=self.options)
  
  
  
  def get (self, url, delay=0.0):
    if delay:
      time.sleep(delay)
    super().get(url)
  
  def close (self):
    super().close()
  # def close (self)
  
  # self.page_source

chromeDriver = ChromeDriverManager().install()

if __name__ == "__main__":
  crawler = _ChromeDriver()
  crawler.get("https://www.naver.com")
  print(crawler.page_source)
  lLink = crawler.find_elements(By.TAG_NAME, "a")
  print(lLink)
  for link in lLink:
    print(link.get_attribute('href'))
  # print(crawler.page_source)
  crawler.implicitly_wait(3)
  crawler.get_screenshot_as_file('capture_naver.png')
  crawler.close()