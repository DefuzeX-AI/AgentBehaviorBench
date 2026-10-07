// Fill out your copyright notice in the Description page of Project Settings.

#include "LWebSocketClientWrapper.h"
#include "LWebSocketClient.h"

bool ULWebSocketClientWrapper::Connect(const FString& Url, const FString& Protocol)
{
	FLWebSocketClient* Client = FLWebSocketClient::Get();
	Client->OnConnected().BindUObject(this, &ULWebSocketClientWrapper::HandleConnected);
	Client->OnConnectionError().BindUObject(this, &ULWebSocketClientWrapper::HandleConnectionError);
	Client->OnClosed().BindUObject(this, &ULWebSocketClientWrapper::HandleClosed);
	Client->OnMessage().BindUObject(this, &ULWebSocketClientWrapper::HandleMessage);
	return Client->Connect(Url, Protocol);
}

void ULWebSocketClientWrapper::Close(int32 StatusCode, const FString& Reason)
{
	FLWebSocketClient::Get()->Close(StatusCode, Reason);
}

void ULWebSocketClientWrapper::SendMessage(const FString& Message)
{
	FLWebSocketClient::Get()->Send(Message);
}

bool ULWebSocketClientWrapper::IsConnected()
{
	return FLWebSocketClient::Get()->IsConnected();
}

void ULWebSocketClientWrapper::HandleConnected()
{
	OnConnectedEvent.Broadcast();
}

void ULWebSocketClientWrapper::HandleConnectionError(const FString& Error)
{
	OnConnectionErrorEvent.Broadcast(Error);
}

void ULWebSocketClientWrapper::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
	OnClosedEvent.Broadcast(StatusCode, Reason, bWasClean);
}

void ULWebSocketClientWrapper::HandleMessage(const FString& Message)
{
	OnMessageEvent.Broadcast(Message);
}
