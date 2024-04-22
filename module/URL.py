import re

def tokenize(sURL):
  if not sURL:
    return []
  
  if len(sURL) > 7 and sURL[:4].lower() == 'http':
    sURL = sURL[6:]
    while sURL[0] in ':/':
      sURL = sURL[1:]
  
  if sURL[-1] == '/':
    sURL = sURL[:-1]
  
  if '#' in sURL:
    sURL = sURL.split('#')[0]
  
  if not sURL:
    return []
  
  lTmpToken = sURL.split('/')
  domain = lTmpToken[0].split('.')
  domain.reverse()
  lURL = domain
  
  if len(lTmpToken) > 1:
    uri = ['^']+ lTmpToken[1:-1]
    qry = lTmpToken[-1].split('?')
  
    if len(qry) > 1:
      uri += qry[0]
      qry = ['~'] + re.split('([&|=])', qry[1])

    uri += qry
    
    lURL += uri
  
  return lURL


if __name__ == "__main__":
  ex = "https://www.naver.com/a/b/c/d?kjh=12&jk=6"
  l = tokenize(ex)
  print(l)
  