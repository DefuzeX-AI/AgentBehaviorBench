// Fill out your copyright notice in the Description page of Project Settings.

#include "LUdpClientWrapper.h"
#include "LUdpClient.h"

bool ULUdpClientWrapper::Start(const FString& SocketName, const int32 LocalPort, const FString& RemoteIP, const int32 RemotePort)
{
	FLUdpClient* Client = FLUdpClient::Get();
	Client->OnDataReceived().BindUObject(this, &ULUdpClientWrapper::HandleDataReceived);
	return Client->Start(SocketName, LocalPort, RemoteIP, RemotePort);
}

void ULUdpClientWrapper::Stop()
{
	FLUdpClient::Get()->Stop();
}

bool ULUdpClientWrapper::SendMessage(const FString& Message)
{
	return FLUdpClient::Get()->Send(Message);
}

bool ULUdpClientWrapper::SendTo(const FString& Message, const FString& RemoteIP, const int32 RemotePort)
{
	const FTCHARToUTF8 Convert(*Message);
	const TArray Data(reinterpret_cast<const uint8*>(Convert.Get()), Convert.Length());
	return FLUdpClient::Get()->SendTo(Data, RemoteIP, RemotePort);
}

bool ULUdpClientWrapper::IsRunning()
{
	return FLUdpClient::Get()->IsRunning();
}

FString ULUdpClientWrapper::GetLocalAddress()
{
	return FLUdpClient::Get()->GetLocalAddress();
}

FString ULUdpClientWrapper::GetRemoteAddress()
{
	return FLUdpClient::Get()->GetRemoteAddress();
}

void ULUdpClientWrapper::HandleDataReceived(const FString& Message, const FString& SenderEndpoint) const
{
	OnMessageReceived.Broadcast(Message, SenderEndpoint);
}
