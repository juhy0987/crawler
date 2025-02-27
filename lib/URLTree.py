import sys

from .Tree import Tree
from . import URL

class URLTree(Tree): # DB, DB3
  def __init__(self):
    super().__init__()
    
  def load(self, lURLs):
    if not lURLs:
      return 0
    
    for sURL in lURLs:
      if self.putURL(sURL[0]) < 0:
        return -1
    
    return 0
  
  def putURL(self, sURL):
    lURL = URL.tokenize(sURL)
    if not lURL:
      return -1
    
    curNode = self
    flag_query = False
    for nIdx in range(len(lURL)):
      token = lURL[nIdx]
      curNode = curNode.put(token)
      
      if token == "~":
        flag_query = True
        lURL = lURL[nIdx+1:]
        break
    
    if flag_query:
      nIdx = 0
      while nIdx < len(lURL)-2:
        try:
          key = lURL[nIdx]
          value = lURL[nIdx+2]
        except ValueError:
          break
        
        keyNode = curNode.put(key)
        valNode = keyNode.put(value)
        
        nIdx += 4
    return 0
    
  def lookupURL(self, sURL):
    if not sURL:
      return -1
    
    lURL = URL.tokenize(sURL)
    
    if not lURL:
      return -1
    
    return self.lookupAll(lURL)

if __name__ == "__main__":
  ex = "https://www.naver.com/a/b/c/d?kjh=12&jk=6"
  # ex = "https://www.naver.com"
  lURL = URL.tokenize(ex)
  tree = URLTree()
  tree.putURL(ex)
  
  tree.print()
  print(tree.lookupURL("https://www.naver.com"))