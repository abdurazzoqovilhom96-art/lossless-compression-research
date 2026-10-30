import struct,zlib
import numpy as np
H=struct.Struct('<4sIIH')
def inflate(p,limit):
 d=zlib.decompressobj();r=d.decompress(p,limit+1)
 if len(r)>limit or not d.eof or d.unused_data or d.unconsumed_tail:raise ValueError('invalid/oversized zlib stream')
 return r
def encode(a,tile=64,spatial=True):
 a=np.asarray(a)
 if a.ndim!=2 or a.dtype!=np.uint16 or not a.size:raise ValueError('nonempty 2D uint16 required')
 if not 1<=tile<=256:raise ValueError('tile')
 h,w=a.shape;out=bytearray(H.pack(b'RVL1',h,w,tile))
 for y in range(0,h,tile):
  for x in range(0,w,tile):
   b=a[y:y+tile,x:x+tile];raw=b.astype('<u2').tobytes();s,inv=np.unique(b,return_inverse=True);inv=inv.reshape(b.shape)
   dt='<u1' if len(s)<=256 else '<u2';ids=inv.astype(dt)
   # Equality with already reconstructed upper pixel; literal IDs only on mismatch.
   same=np.zeros(b.shape,dtype=bool);same[1:]=b[1:]==b[:-1]
   mask=np.packbits(same.ravel(),bitorder='little').tobytes()
   palette=struct.pack('<I',len(s))+s.astype('<u2').tobytes()
   candidates=[raw,zlib.compress(raw,6),palette+zlib.compress(ids.tobytes(),6),palette+zlib.compress(mask+ids[~same].tobytes(),6)]
   m=min(range(4 if spatial else 3),key=lambda k:(len(candidates[k]),k));p=candidates[m]
   out+=struct.pack('<BI',m,len(p))+p
 return bytes(out)+struct.pack('<I',zlib.crc32(a.astype('<u2').tobytes()))
def decode(data):
 if len(data)<H.size+4:raise ValueError('truncated')
 magic,h,w,t=H.unpack_from(data)
 if magic!=b'RVL1' or not h or not w or h*w>100000000 or not 1<=t<=256:raise ValueError('header')
 out=np.empty((h,w),np.uint16);pos=H.size
 for y in range(0,h,t):
  for x in range(0,w,t):
   bh,bw=min(t,h-y),min(t,w-x);n=bh*bw
   if pos+5>len(data)-4:raise ValueError('record')
   m,l=struct.unpack_from('<BI',data,pos);pos+=5
   if pos+l>len(data)-4:raise ValueError('length')
   p=data[pos:pos+l];pos+=l
   if m in (0,1):
    r=p if m==0 else inflate(p,2*n)
    if len(r)!=2*n:raise ValueError('raw length')
    b=np.frombuffer(r,'<u2').reshape(bh,bw)
   elif m in (2,3):
    k=struct.unpack_from('<I',p)[0]
    if not 1<=k<=min(n,65536):raise ValueError('palette')
    s=np.frombuffer(p[4:4+2*k],'<u2')
    if len(s)!=k or np.any(s[1:]<=s[:-1]):raise ValueError('palette order')
    r=inflate(p[4+2*k:],2*n+(n+7)//8);dt='<u1' if k<=256 else '<u2'
    if m==2:
     ids=np.frombuffer(r,dt)
     if len(ids)!=n or np.any(ids>=k):raise ValueError('indices')
     b=s[ids].reshape(bh,bw)
    else:
     nb=(n+7)//8;mask=np.unpackbits(np.frombuffer(r[:nb],np.uint8),bitorder='little')[:n].reshape(bh,bw)
     if np.any(mask[0]):raise ValueError('first row')
     ids=np.frombuffer(r[nb:],dt)
     if len(ids)!=n-int(mask.sum()) or np.any(ids>=k):raise ValueError('literals')
     b=np.empty((bh,bw),np.uint16);j=0
     for yy in range(bh):
      literal=mask[yy]==0;count=int(literal.sum())
      b[yy,literal]=s[ids[j:j+count]];j+=count
      if yy:b[yy,~literal]=b[yy-1,~literal]
   else:raise ValueError('mode')
   out[y:y+bh,x:x+bw]=b
 if pos!=len(data)-4 or zlib.crc32(out.astype('<u2').tobytes())!=struct.unpack_from('<I',data,pos)[0]:raise ValueError('CRC/EOF')
 return out
