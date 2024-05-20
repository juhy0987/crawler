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
  
  while True:
    try:
      lURL.remove("")
    except ValueError:
      break
  
  if lURL[-1] == '^' or lURL[-1] == '~':
    lURL = lURL[:-1]
  
  return lURL

def regexTokenize(sURLRegex):
  if not sURLRegex:
    return []
  
  if len(sURLRegex) > 7 and sURLRegex[:4].lower() == 'http':
    sURLRegex = sURLRegex[6:]
    while sURLRegex[0] in ':/':
      sURLRegex = sURLRegex[1:]
  
  if sURLRegex[-1] == '/':
    sURLRegex = sURLRegex[:-1]
  
  if '#' in sURLRegex:
    sURLRegex = sURLRegex.split('#')[0]
  
  if not sURLRegex:
    return []
  
  lTmpToken = re.split('\/', sURLRegex)
  domain = re.split('\.', lTmpToken[0])
  domain.reverse()
  lURL = domain
  
  if len(lTmpToken) > 1:
    uri = ['\^']+ lTmpToken[1:-1]
    qry = lTmpToken[-1].split('?')
  
    if len(qry) > 1:
      uri += qry[0]
      qry = ['~'] + re.split('([&|=])', qry[1])

    uri += qry
    
    lURL += uri
  
  while True:
    try:
      lURL.remove("")
    except ValueError:
      break
  
  if lURL[-1] == '\^' or lURL[-1] == '~':
    lURL = lURL[:-1]
  
  return lURL

def getProtocolHost(sURL):
  if not sURL:
    return ""
  
  protocol = ""
  if len(sURL) > 7 and sURL[:4].lower() == 'http':
    protocol = sURL[:6]
    sURL = sURL[6:]
    while sURL[0] in ':/':
      protocol = protocol + sURL[0]
      sURL = sURL[1:]
  
  if '#' in sURL:
    sURL = sURL.split('#')[0]
  
  if not sURL:
    return ""
  
  lTmpToken = sURL.split('/', 1)[0] + "/"
  return protocol + lTmpToken

def getHost(sURL):
  if not sURL:
    return ""
  
  if len(sURL) > 7 and sURL[:4].lower() == 'http':
    sURL = sURL[6:]
    while sURL[0] in ':/':
      sURL = sURL[1:]
  
  if '#' in sURL:
    sURL = sURL.split('#')[0]
  
  if not sURL:
    return ""
  
  lTmpToken = sURL.split('/', 1)[0]
  return lTmpToken

if __name__ == "__main__":
  ex = "https://www.naver.com/a/b/c/d?kjh=12&jk=6"
  l = getHost(ex)
  print(l)
  