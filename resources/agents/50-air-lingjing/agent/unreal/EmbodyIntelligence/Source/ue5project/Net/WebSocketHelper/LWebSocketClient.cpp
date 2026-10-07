// Fill out your copyright notice in the Description page of Project Settings.

#include "LWebSocketClient.h"

#include "IWebSocket.h"
#include "WebSocketsModule.h"

FLWebSocketClient::~FLWebSocketClient()
{
	Close();
}

FLWebSocketClient* FLWebSocketClient::Get()
{
	static FLWebSocketClient Instance;
	return &Instance;
}

bool FLWebSocketClient::Connect(const FString& InUrl, const FString& InProtocol)
{
	if (WebSocket.IsValid() && WebSocket->IsConnected())
	{
		return true;
	}

	if (!FModuleManager::Get().IsModuleLoaded("WebSockets"))
	{
		FModuleManager::Get().LoadModule("WebSockets");
	}

	TArray<FString> Protocols;
	Protocols.Add(InProtocol);

	WebSocket = FWebSocketsModule::Get().CreateWebSocket(InUrl, Protocols);
	if (!WebSocket.IsValid())
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Red, FString::Printf(TEXT("LWebSocketClient: Failed to create WebSocket for %s"), *InUrl));
		return false;
	}

	WebSocket->OnConnected().AddRaw(this, &FLWebSocketClient::HandleConnected);
	WebSocket->OnConnectionError().AddRaw(this, &FLWebSocketClient::HandleConnectionError);
	WebSocket->OnClosed().AddRaw(this, &FLWebSocketClient::HandleClosed);
	WebSocket->OnMessage().AddRaw(this, &FLWebSocketClient::HandleMessage);

	WebSocket->Connect();
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Green, FString::Printf(TEXT("LWebSocketClient: Connecting to %s"), *InUrl));

	return true;
}

void FLWebSocketClient::Close(const int32 StatusCode, const FString& Reason) const
{
	if (WebSocket.IsValid())
	{
		WebSocket->Close(StatusCode, Reason);
	}
}

void FLWebSocketClient::Send(const FString& Message) const
{
	if (WebSocket.IsValid() && WebSocket->IsConnected())
	{
		WebSocket->Send(Message);
	}
}

void FLWebSocketClient::SendRaw(const TArray<uint8>& Data) const
{
	if (WebSocket.IsValid() && WebSocket->IsConnected())
	{
		WebSocket->Send(Data.GetData(), Data.Num(), true);
	}
}

bool FLWebSocketClient::IsConnected() const
{
	return WebSocket.IsValid() && WebSocket->IsConnected();
}

void FLWebSocketClient::HandleConnected() const
{
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Green, TEXT("LWebSocketClient: Connected"));
	ConnectedDelegate.ExecuteIfBound();
}

void FLWebSocketClient::HandleConnectionError(const FString& Error) const
{
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Red, FString::Printf(TEXT("LWebSocketClient: Connection error: %s"), *Error));
	ConnectionErrorDelegate.ExecuteIfBound(Error);
}

void FLWebSocketClient::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean) const
{
	GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Red, FString::Printf(TEXT("LWebSocketClient: Closed (%d, %s, %s)"), 
		StatusCode, *Reason, bWasClean ? TEXT("clean") : TEXT("unclean")));
	ClosedDelegate.ExecuteIfBound(StatusCode, Reason, bWasClean);
}

void FLWebSocketClient::HandleMessage(const FString& Message) const
{
	MessageDelegate.ExecuteIfBound(Message);
}
