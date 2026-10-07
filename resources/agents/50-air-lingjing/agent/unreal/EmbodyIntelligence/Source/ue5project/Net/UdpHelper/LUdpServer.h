// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Common/UdpSocketReceiver.h"
#include "Common/UdpSocketSender.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"

DECLARE_DELEGATE_TwoParams(FOnUdpServerDataReceived, const FString& /*Message*/, const FString& /*SenderEndpoint*/);

class UE5PROJECT_API FLUdpServer
{
public:
	static FLUdpServer* Get();

	bool Start(const FString& InSocketName, int32 InLocalPort);
	void Stop();

	bool SendTo(const TArray<uint8>& Data, const FString& RemoteIP, int32 RemotePort) const;
	bool SendTo(const FString& Message, const FString& RemoteIP, int32 RemotePort) const;

	FOnUdpServerDataReceived& OnDataReceived() { return DataReceivedDelegate; }

	bool IsRunning() const { return bIsRunning; }
	FString GetLocalAddress() const;

private:
	~FLUdpServer();

	void HandleDataReceived(const FArrayReaderPtr& Data, const FIPv4Endpoint& Endpoint) const;

	FSocket* UdpSocket = nullptr;
	TSharedPtr<FUdpSocketReceiver> SocketReceiver;
	FIPv4Endpoint LocalEndpoint;
	FOnUdpServerDataReceived DataReceivedDelegate;
	bool bIsRunning = false;
};
