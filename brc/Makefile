CC = g++ -fPIC -Wall -ansi `pkg-config --cflags libbitcoin` -I/usr/include/python2.7 

default:
	$(CC) -c brc.cpp -o brc.o
	$(CC) -shared -Wl,-soname,_brc.so brc.o -lpython2.7 -lboost_python `pkg-config --libs libbitcoin` -lboost_thread -o _brc.so

