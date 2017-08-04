import socket

HOST = socket.gethostbyname('192.168.1.8')
PORT = 8493

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    print(HOST)
    s.connect((HOST, PORT))
    s.sendall(b'v03f0203,f0206,f0811')
    data = s.recv(1024)

print('Received %r' % data)
