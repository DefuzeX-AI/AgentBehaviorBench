// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

class IWebSocketServer;
class INetworkingWebSocket;
DECLARE_DELEGATE_OneParam(FOnWsClientConnected, const FString& /*ClientId*/);
DECLARE_DELEGATE_TwoParams(FOnWsClientDisconnected, const FString& /*ClientId*/, int32 /*StatusCode*/);
DECLARE_DELEGATE_TwoParams(FOnWsServerMessage, const FString& /*ClientId*/, const FString& /*Message*/);

class UE5PROJECT_API FLWebSocketServer
{
public:
	static FLWebSocketServer* Get();

	bool Start(int32 Port);
	void Stop();
	bool Broadcast(const FString& Message) const;
	bool SendToClient(const FString& ClientId, const FString& Message) const;

	FOnWsClientConnected& OnClientConnected() { return ClientConnectedDelegate; }
	FOnWsClientDisconnected& OnClientDisconnected() { return ClientDisconnectedDelegate; }
	FOnWsServerMessage& OnMessage() { return MessageDelegate; }

	bool IsRunning() const;
	int32 GetPort() const { return ServerPort; }

private:
	FLWebSocketServer();
	~FLWebSocketServer();
	FLWebSocketServer(const FLWebSocketServer&) = delete;
	FLWebSocketServer& operator=(const FLWebSocketServer&) = delete;

	FString GenerateClientId() const;
	void HandleClientConnected(INetworkingWebSocket* Socket);

	TUniquePtr<IWebSocketServer> Server;
	TMap<FString, INetworkingWebSocket*> Clients;
	FOnWsClientConnected ClientConnectedDelegate;
	FOnWsClientDisconnected ClientDisconnectedDelegate;
	FOnWsServerMessage MessageDelegate;
	FTSTicker::FDelegateHandle TickerHandle;
	int32 ServerPort = 0;
	bool bIsRunning = false;
};
