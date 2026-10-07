// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

class IWebSocket;
DECLARE_DELEGATE(FOnWsConnected);
DECLARE_DELEGATE_OneParam(FOnWsConnectionError, const FString& /*Error*/);
DECLARE_DELEGATE_ThreeParams(FOnWsClosed, const int32 /*StatusCode*/, const FString& /*Reason*/, const bool /*bWasClean*/);
DECLARE_DELEGATE_OneParam(FOnWsMessage, const FString& /*Message*/);

class UE5PROJECT_API FLWebSocketClient
{
public:
	static FLWebSocketClient* Get();

	bool Connect(const FString& InUrl, const FString& InProtocol = TEXT("ws"));
	void Close(int32 StatusCode = 1000, const FString& Reason = TEXT("")) const;
	void Send(const FString& Message) const;
	void SendRaw(const TArray<uint8>& Data) const;

	FOnWsConnected& OnConnected() { return ConnectedDelegate; }
	FOnWsConnectionError& OnConnectionError() { return ConnectionErrorDelegate; }
	FOnWsClosed& OnClosed() { return ClosedDelegate; }
	FOnWsMessage& OnMessage() { return MessageDelegate; }

	bool IsConnected() const;

private:
	FLWebSocketClient() = default;
	~FLWebSocketClient();

	void HandleConnected() const;
	void HandleConnectionError(const FString& Error) const;
	void HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean) const;
	void HandleMessage(const FString& Message) const;

	TSharedPtr<IWebSocket> WebSocket;
	FOnWsConnected ConnectedDelegate;
	FOnWsConnectionError ConnectionErrorDelegate;
	FOnWsClosed ClosedDelegate;
	FOnWsMessage MessageDelegate;
};
