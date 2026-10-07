// Fill out your copyright notice in the Description page of Project Settings.

#include "LUdpServerWrapper.h"
#include "LUdpServer.h"

bool ULUdpServerWrapper::Start(const FString& SocketName, const int32 LocalPort)
{
	FLUdpServer* Server = FLUdpServer::Get();
	Server->OnDataReceived().BindUObject(this, &ULUdpServerWrapper::HandleDataReceived);
	return Server->Start(SocketName, LocalPort);
}

void ULUdpServerWrapper::Stop()
{
	FLUdpServer::Get()->Stop();
}

bool ULUdpServerWrapper::SendTo(const FString& Message, const FString& RemoteIP, const int32 RemotePort)
{
	return FLUdpServer::Get()->SendTo(Message, RemoteIP, RemotePort);
}

bool ULUdpServerWrapper::IsRunning()
{
	return FLUdpServer::Get()->IsRunning();
}

FString ULUdpServerWrapper::GetLocalAddress()
{
	return FLUdpServer::Get()->GetLocalAddress();
}

void ULUdpServerWrapper::HandleDataReceived(const FString& Message, const FString& SenderEndpoint) const
{
	OnMessageReceived.Broadcast(Message, SenderEndpoint);
}
