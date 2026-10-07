// Fill out your copyright notice in the Description page of Project Settings.

#include "LWebSocketServerWrapper.h"
#include "LWebSocketServer.h"

bool ULWebSocketServerWrapper::Start(const int32 Port)
{
	FLWebSocketServer* Server = FLWebSocketServer::Get();
	Server->OnClientConnected().BindUObject(this, &ULWebSocketServerWrapper::HandleClientConnected);
	Server->OnClientDisconnected().BindUObject(this, &ULWebSocketServerWrapper::HandleClientDisconnected);
	Server->OnMessage().BindUObject(this, &ULWebSocketServerWrapper::HandleMessage);
	return Server->Start(Port);
}

void ULWebSocketServerWrapper::Stop()
{
	FLWebSocketServer::Get()->Stop();
}

bool ULWebSocketServerWrapper::Broadcast(const FString& Message)
{
	return FLWebSocketServer::Get()->Broadcast(Message);
}

bool ULWebSocketServerWrapper::SendToClient(const FString& ClientId, const FString& Message)
{
	return FLWebSocketServer::Get()->SendToClient(ClientId, Message);
}

bool ULWebSocketServerWrapper::IsRunning()
{
	return FLWebSocketServer::Get()->IsRunning();
}

void ULWebSocketServerWrapper::HandleClientConnected(const FString& ClientId)
{
	OnClientConnectedEvent.Broadcast(ClientId);
}

void ULWebSocketServerWrapper::HandleClientDisconnected(const FString& ClientId, int32 StatusCode)
{
	OnClientDisconnectedEvent.Broadcast(ClientId, StatusCode);
}

void ULWebSocketServerWrapper::HandleMessage(const FString& ClientId, const FString& Message)
{
	OnMessageEvent.Broadcast(ClientId, Message);
}
