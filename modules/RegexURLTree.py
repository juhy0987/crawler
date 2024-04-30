import re

from . import URL
from .Tree import Node
from .URLTree import URLTree

class RegexTree(URLTree):
  def lookup(self, token): # return : node, if not: none
    if not token:
      return None
    
    for key in self.children.keys():
      if re.match(key, token):
        return self.children[key]
    
    
    try:
      curNode = self.children[token]
    except KeyError:
      return None
    else:
      return curNode

  def putURL(self, sURLRegex):
    lURL = URL.regexTokenize(sURLRegex)
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