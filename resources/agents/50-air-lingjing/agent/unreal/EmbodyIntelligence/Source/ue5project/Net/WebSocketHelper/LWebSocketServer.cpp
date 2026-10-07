// Fill out your copyright notice in the Description page of Project Settings.

#include "LWebSocketServer.h"
#include "IWebSocketNetworkingModule.h"
#include "IWebSocketServer.h"
#include "INetworkingWebSocket.h"
#include "Modules/ModuleManager.h"

FLWebSocketServer::FLWebSocketServer() = default;

FLWebSocketServer::~FLWebSocketServer()
{
	Stop();
}

FLWebSocketServer* FLWebSocketServer::Get()
{
	static FLWebSocketServer Instance;
	return &Instance;
}

bool FLWebSocketServer::Start(int32 Port)
{
	if (bIsRunning)
	{
		return true;
	}

	IWebSocketNetworkingModule* WsNetModule = FModuleManager::Get().LoadModulePtr<IWebSocketNetworkingModule>(TEXT("WebSocketNetworking"));
	if (!WsNetModule)
	{
		UE_LOG(LogTemp, Error, TEXT("LWebSocketServer: Failed to load WebSocketNetworking module"));
		return false;
	}

	Server = WsNetModule->CreateServer();
	if (!Server)
	{
		UE_LOG(LogTemp, Error, TEXT("LWebSocketServer: Failed to create server"));
		return false;
	}

	if (!Server->Init(Port, FWebSocketClientConnectedCallBack::CreateRaw(this, &FLWebSocketServer::HandleClientConnected)))
	{
		UE_LOG(LogTemp, Error, TEXT("LWebSocketServer: Failed to init on port %d"), Port);
		Server.Reset();
		return false;
	}

	ServerPort = Port;

	TickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([this](float)
	{
		if (Server)
		{
			Server->Tick();
		}
		return true;
	}));

	bIsRunning = true;
	UE_LOG(LogTemp, Log, TEXT("LWebSocketServer: Started on port %d"), Port);
	return true;
}

void FLWebSocketServer::Stop()
{
	if (!bIsRunning)
	{
		return;
	}

	if (TickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickerHandle);
		TickerHandle.Reset();
	}

	Clients.Empty();
	Server.Reset();

	bIsRunning = false;
	UE_LOG(LogTemp, Log, TEXT("LWebSocketServer: Stopped"));
}

bool FLWebSocketServer::Broadcast(const FString& Message) const
{
	if (!bIsRunning || Clients.Num() == 0)
	{
		return false;
	}

	const FTCHARToUTF8 Convert(*Message);
	for (const auto& Pair : Clients)
	{
		if (Pair.Value)
		{
			Pair.Value->Send(reinterpret_cast<const uint8*>(Convert.Get()), Convert.Length(), false);
		}
	}
	return true;
}

bool FLWebSocketServer::SendToClient(const FString& ClientId, const FString& Message) const
{
	if (!bIsRunning)
	{
		return false;
	}

	INetworkingWebSocket* const* Client = Clients.Find(ClientId);
	if (!Client || !*Client)
	{
		return false;
	}

	const FTCHARToUTF8 Convert(*Message);
	(*Client)->Send(reinterpret_cast<const uint8*>(Convert.Get()), Convert.Length(), false);
	return true;
}

bool FLWebSocketServer::IsRunning() const
{
	return bIsRunning;
}

FString FLWebSocketServer::GenerateClientId() const
{
	return FGuid::NewGuid().ToString(EGuidFormats::Digits);
}

void FLWebSocketServer::HandleClientConnected(INetworkingWebSocket* Socket)
{
	const FString ClientId = GenerateClientId();

	Socket->SetReceiveCallBack(FWebSocketPacketReceivedCallBack::CreateLambda([this, ClientId](void* Data, int32 DataSize)
	{
		const FString Message(UTF8_TO_TCHAR(static_cast<const char*>(Data)));
		MessageDelegate.ExecuteIfBound(ClientId, Message);
	}));

	Socket->SetSocketClosedCallBack(FWebSocketInfoCallBack::CreateLambda([this, ClientId]()
	{
		UE_LOG(LogTemp, Log, TEXT("LWebSocketServer: Client disconnected %s"), *ClientId);
		Clients.Remove(ClientId);
		ClientDisconnectedDelegate.ExecuteIfBound(ClientId, 0);
	}));

	Clients.Add(ClientId, Socket);

	UE_LOG(LogTemp, Log, TEXT("LWebSocketServer: Client connected %s"), *ClientId);
	ClientConnectedDelegate.ExecuteIfBound(ClientId);
}
