// Copyright 2022 The Forgotten Server Authors. All rights reserved.
// Use of this source code is governed by the GPL-2.0 License that can be found in the LICENSE file.

#include "otpch.h"

#include <iostream>
#include <vector>

#include "protocol.h"
#include "outputmessage.h"
#include "rsa.h"
#include "xtea.h"

namespace {

void XTEA_encrypt(OutputMessage& msg, const xtea::round_keys& key)
{
	// The message must be a multiple of 8
	size_t paddingBytes = msg.getLength() % 8u;
	if (paddingBytes != 0) {
		msg.addPaddingBytes(8 - paddingBytes);
	}

	uint8_t* buffer = msg.getOutputBuffer();
	xtea::encrypt(buffer, msg.getLength(), key);
}

bool XTEA_decrypt(NetworkMessage& msg, const xtea::round_keys& key)
{
	if (((msg.getLength() - 6) & 7) != 0) {
		return false;
	}

	uint8_t* buffer = msg.getBuffer() + msg.getBufferPosition();
	xtea::decrypt(buffer, msg.getLength() - 6, key);

	uint16_t innerLength = msg.get<uint16_t>();
	if (innerLength + 8 > msg.getLength()) {
		return false;
	}

	msg.setLength(innerLength);
	return true;
}

}

void Protocol::onSendMessage(const OutputMessage_ptr& msg) const
{
	if (!rawMessages) {
		bool compressed = false;
		if (compression && msg->getLength() > 64) {
			compress(*msg);
			compressed = true;
		}
		msg->writeMessageLength();

		if (encryptionEnabled) {
			XTEA_encrypt(*msg, key);
			msg->addCryptoHeader(checksumEnabled, compressed);
		}
	}
}

void Protocol::onRecvMessage(NetworkMessage& msg)
{
	if (encryptionEnabled && !XTEA_decrypt(msg, key)) {
		return;
	}

	parsePacket(msg);
}

OutputMessage_ptr Protocol::getOutputBuffer(int32_t size)
{
	//dispatcher thread
	if (!outputBuffer) {
		outputBuffer = OutputMessagePool::getOutputMessage();
	} else if ((outputBuffer->getLength() + size) > NetworkMessage::MAX_PROTOCOL_BODY_LENGTH) {
		send(outputBuffer);
		outputBuffer = OutputMessagePool::getOutputMessage();
	}
	return outputBuffer;
}

bool Protocol::RSA_decrypt(NetworkMessage& msg)
{
	if (msg.getRemainingBufferLength() < RSA_BUFFER_LENGTH) {
		return false;
	}

	tfs::rsa::decrypt(msg.getRemainingBuffer(), RSA_BUFFER_LENGTH);
	return msg.getByte() == 0;
}

uint32_t Protocol::getIP() const
{
	if (auto connection = getConnection()) {
		return connection->getIP();
	}

	return 0;
}

bool Protocol::isOtcProxy() const
{
	if (auto connection = getConnection()) {
		return connection->isOtcProxy();
	}

	return false;
}

bool Protocol::isHaProxy() const
{
	if (auto connection = getConnection()) {
		return connection->isHaProxy();
	}

	return false;
}


void Protocol::enableCompression()
{
	if (compression) {
		return;
	}
	if (deflateInit2(&zstream, 6, Z_DEFLATED, -15, 8, Z_DEFAULT_STRATEGY) != Z_OK) {
		std::cerr << "ZLIB initialization error: " << (zstream.msg ? zstream.msg : "unknown") << std::endl;
		return;
	}
	compression = true;
}

void Protocol::compress(OutputMessage& msg) const
{
	static thread_local std::vector<uint8_t> buffer(NETWORKMESSAGE_MAXSIZE);
	zstream.next_in = msg.getOutputBuffer();
	zstream.avail_in = msg.getLength();
	zstream.next_out = buffer.data();
	zstream.avail_out = static_cast<uInt>(buffer.size());
	if (deflate(&zstream, Z_SYNC_FLUSH) != Z_OK) {
		std::cerr << "ZLIB deflate error: " << (zstream.msg ? zstream.msg : "unknown") << std::endl;
		return;
	}
	int finalSize = static_cast<int>(buffer.size()) - static_cast<int>(zstream.avail_out) - 4;
	if (finalSize < 0) {
		std::cerr << "Packet compression error: " << (zstream.msg ? zstream.msg : "unknown") << std::endl;
		return;
	}

	msg.reset();
	msg.addBytes(reinterpret_cast<const char*>(buffer.data()), finalSize);
}
