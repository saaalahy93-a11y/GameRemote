// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include <gameremote/sock.h>
#include <fcntl.h>
#ifndef _WIN32
#include <sys/socket.h>
#endif

CHIAKI_EXPORT ChiakiErrorCode chiaki_socket_set_recvbuf(chiaki_socket_t sock, int preferred, int fallback)
{
	if(fallback <= 0 || preferred < fallback)
		return CHIAKI_ERR_INVALID_DATA;
	if(setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (const CHIAKI_SOCKET_BUF_TYPE)&preferred, sizeof(preferred)) == 0)
		return CHIAKI_ERR_SUCCESS;
	if(preferred != fallback
			&& setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (const CHIAKI_SOCKET_BUF_TYPE)&fallback, sizeof(fallback)) == 0)
		return CHIAKI_ERR_SUCCESS;
	return CHIAKI_ERR_NETWORK;
}

CHIAKI_EXPORT ChiakiErrorCode chiaki_socket_set_nonblock(chiaki_socket_t sock, bool nonblock)
{
#ifdef _WIN32
	u_long nbio = nonblock ? 1 : 0;
	if(ioctlsocket(sock, FIONBIO, &nbio) != NO_ERROR)
		return CHIAKI_ERR_UNKNOWN;
#else
	int flags = fcntl(sock, F_GETFL, 0);
	if(flags == -1)
		return CHIAKI_ERR_UNKNOWN;
	flags = nonblock ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
	if(fcntl(sock, F_SETFL, flags) == -1)
		return CHIAKI_ERR_UNKNOWN;
#endif
	return CHIAKI_ERR_SUCCESS;
}
