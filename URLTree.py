from module import Tree

class URLTree(Tree):
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
    
  def lookupURL(self, sURL):
    if not sURL:
      return -1
    
    lURL = URL.tokenize(sURL)
    
    if not lURL:
      return 0
    
    self.lookupAll

if __name__ == "__main__":
  from module import URL
  ex = "https://www.naver.com/a/b/c/d?kjh=12&jk=6"
  lURL = URL.tokenize(ex)
  tree = URLTree()
  tree.putURL(ex)
  
  tree.print()