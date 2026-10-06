// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include <munit.h>
#include <gameremote/sock.h>
#include <limits.h>
#ifndef _WIN32
#include <sys/socket.h>
#include <netinet/in.h>
#endif

static void *socket_setup(const MunitParameter params[], void *user)
{
#ifdef _WIN32
	WSADATA data;
	munit_assert_int(WSAStartup(MAKEWORD(2, 2), &data), ==, 0);
#endif
	return NULL;
}

static void socket_teardown(void *fixture)
{
#ifdef _WIN32
	WSACleanup();
#endif
}

static int receive_capacity(chiaki_socket_t sock)
{
	int value = 0;
#ifdef _WIN32
	int size = sizeof(value);
#else
	socklen_t size = sizeof(value);
#endif
	munit_assert_int(getsockopt(sock, SOL_SOCKET, SO_RCVBUF, (CHIAKI_SOCKET_BUF_TYPE)&value, &size), ==, 0);
	return value;
}

static MunitResult test_preferred_capacity(const MunitParameter params[], void *user)
{
	chiaki_socket_t sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
	munit_assert_false(CHIAKI_SOCKET_IS_INVALID(sock));
	int preferred = 1024 * 1024;
	if(setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (const CHIAKI_SOCKET_BUF_TYPE)&preferred, sizeof(preferred)) != 0)
	{
		CHIAKI_SOCKET_CLOSE(sock);
		return MUNIT_SKIP; // The fallback case covers hosts that reject this preference.
	}
	int expected = receive_capacity(sock);
	int baseline = 0x19000;
	munit_assert_int(setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (const CHIAKI_SOCKET_BUF_TYPE)&baseline, sizeof(baseline)), ==, 0);
	munit_assert_int(chiaki_socket_set_recvbuf(sock, 1024 * 1024, 0x19000), ==, CHIAKI_ERR_SUCCESS);
	// Compare with the same kernel's direct result, including any permitted clamp.
	munit_assert_int(receive_capacity(sock), ==, expected);
	CHIAKI_SOCKET_CLOSE(sock);
	return MUNIT_OK;
}

static MunitResult test_rejected_preference_falls_back(const MunitParameter params[], void *user)
{
	chiaki_socket_t sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
	munit_assert_false(CHIAKI_SOCKET_IS_INVALID(sock));
	int rejected_size = INT_MAX;
	int result = setsockopt(sock, SOL_SOCKET, SO_RCVBUF, (const CHIAKI_SOCKET_BUF_TYPE)&rejected_size, sizeof(rejected_size));
	if(result == 0)
	{
		CHIAKI_SOCKET_CLOSE(sock);
		return MUNIT_SKIP; // This kernel clamps rather than rejecting the oversized request.
	}
	munit_assert_int(chiaki_socket_set_recvbuf(sock, rejected_size, 0x19000), ==, CHIAKI_ERR_SUCCESS);
	munit_assert_int(receive_capacity(sock), >=, 0x19000);
	CHIAKI_SOCKET_CLOSE(sock);
	return MUNIT_OK;
}

static MunitResult test_invalid_socket_and_sizes(const MunitParameter params[], void *user)
{
	munit_assert_int(chiaki_socket_set_recvbuf(CHIAKI_INVALID_SOCKET, 1024 * 1024, 0x19000), ==, CHIAKI_ERR_NETWORK);
	munit_assert_int(chiaki_socket_set_recvbuf(CHIAKI_INVALID_SOCKET, 0x19000, 0x19000), ==, CHIAKI_ERR_NETWORK);
	munit_assert_int(chiaki_socket_set_recvbuf(CHIAKI_INVALID_SOCKET, 1, 2), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_socket_set_recvbuf(CHIAKI_INVALID_SOCKET, 1, 0), ==, CHIAKI_ERR_INVALID_DATA);
	return MUNIT_OK;
}

MunitTest tests_sock[] = {
	{ "/preferred_capacity", test_preferred_capacity, socket_setup, socket_teardown, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/rejected_preference_falls_back", test_rejected_preference_falls_back, socket_setup, socket_teardown, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/invalid_socket_and_sizes", test_invalid_socket_and_sizes, socket_setup, socket_teardown, MUNIT_TEST_OPTION_NONE, NULL },
	{ NULL, NULL, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL }
};
