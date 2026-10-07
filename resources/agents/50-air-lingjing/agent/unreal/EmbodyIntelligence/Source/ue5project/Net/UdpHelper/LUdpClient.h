// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Common/UdpSocketReceiver.h"
#include "Common/UdpSocketSender.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"

DECLARE_DELEGATE_TwoParams(FOnUdpDataReceived, const FString& /*Message*/, const FString& /*SenderEndpoint*/);

class UE5PROJECT_API FLUdpClient
{
public:
	static FLUdpClient* Get();

	bool Start(const FString& InSocketName, int32 InLocalPort, const FString& InRemoteIP, int32 InRemotePort);
	void Stop();

	bool Send(const TArray<uint8>& Data) const;
	bool Send(const FString& Message) const;
	bool SendTo(const TArray<uint8>& Data, const FString& RemoteIP, int32 RemotePort) const;

	FOnUdpDataReceived& OnDataReceived() { return DataReceivedDelegate; }

	bool IsRunning() const { return bIsRunning; }
	FString GetLocalAddress() const;
	FString GetRemoteAddress() const;

private:
	~FLUdpClient();

	void HandleDataReceived(const FArrayReaderPtr& Data, const FIPv4Endpoint& Endpoint) const;

	FSocket* UdpSocket = nullptr;
	TSharedPtr<FUdpSocketReceiver> SocketReceiver;
	FIPv4Endpoint LocalEndpoint;
	FIPv4Endpoint RemoteEndpoint;
	FOnUdpDataReceived DataReceivedDelegate;
	bool bIsRunning = false;
};
