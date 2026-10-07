// Fill out your copyright notice in the Description page of Project Settings.

#include "LUdpServer.h"
#include "SocketSubsystem.h"
#include "Common/UdpSocketBuilder.h"

FLUdpServer::~FLUdpServer()
{
	Stop();
}

FLUdpServer* FLUdpServer::Get()
{
	static FLUdpServer Instance;
	return &Instance;
}

bool FLUdpServer::Start(const FString& InSocketName, const int32 InLocalPort)
{
	if (bIsRunning)
	{
		return true;
	}

	ISocketSubsystem* SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SocketSubsystem)
	{
		UE_LOG(LogTemp, Error, TEXT("LUdpServer: Failed to get socket subsystem"));
		return false;
	}

	UdpSocket = FUdpSocketBuilder(*InSocketName)
		.AsNonBlocking()
		.AsReusable()
		.WithReceiveBufferSize(2 * 1024 * 1024)
		.WithSendBufferSize(2 * 1024 * 1024)
		.BoundToPort(InLocalPort)
		.Build();

	if (!UdpSocket)
	{
		UE_LOG(LogTemp, Error, TEXT("LUdpServer: Failed to create socket on port %d"), InLocalPort);
		return false;
	}

	const TSharedRef<FInternetAddr> LocalAddr = SocketSubsystem->GetLocalBindAddr(*GLog);
	const int32 BoundPort = UdpSocket->GetPortNo();
	LocalAddr->SetPort(BoundPort);
	LocalEndpoint = FIPv4Endpoint(LocalAddr);

	SocketReceiver = MakeShared<FUdpSocketReceiver>(UdpSocket, FTimespan::FromMilliseconds(100), *InSocketName);
	SocketReceiver->OnDataReceived().BindRaw(this, &FLUdpServer::HandleDataReceived);
	SocketReceiver->Start();

	bIsRunning = true;
	UE_LOG(LogTemp, Log, TEXT("LUdpServer: Started on %s"), *LocalEndpoint.ToString());
	return true;
}

void FLUdpServer::Stop()
{
	if (!bIsRunning)
	{
		return;
	}

	if (SocketReceiver.IsValid())
	{
		SocketReceiver->Stop();
		SocketReceiver.Reset();
	}

	if (UdpSocket)
	{
		if (ISocketSubsystem* SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM))
		{
			SocketSubsystem->DestroySocket(UdpSocket);
		}
		UdpSocket = nullptr;
	}

	bIsRunning = false;
	UE_LOG(LogTemp, Log, TEXT("LUdpServer: Stopped"));
}

bool FLUdpServer::SendTo(const TArray<uint8>& Data, const FString& RemoteIP, int32 RemotePort) const
{
	if (!bIsRunning || !UdpSocket || Data.Num() == 0)
	{
		return false;
	}

	FIPv4Address Addr;
	if (!FIPv4Address::Parse(RemoteIP, Addr))
	{
		return false;
	}

	const FIPv4Endpoint TargetEndpoint(Addr, RemotePort);
	int32 BytesSent = 0;
	return UdpSocket->SendTo(Data.GetData(), Data.Num(), BytesSent, *TargetEndpoint.ToInternetAddr());
}

bool FLUdpServer::SendTo(const FString& Message, const FString& RemoteIP, const int32 RemotePort) const
{
	const FTCHARToUTF8 Convert(*Message);
	const TArray Data(reinterpret_cast<const uint8*>(Convert.Get()), Convert.Length());
	return SendTo(Data, RemoteIP, RemotePort);
}

void FLUdpServer::HandleDataReceived(const FArrayReaderPtr& Data, const FIPv4Endpoint& Endpoint) const
{
	const int32 DataLen = Data->Num();
	auto Converter = StringCast<TCHAR>(reinterpret_cast<const UTF8CHAR*>(Data->GetData()), DataLen);
	const FString Message(Converter.Length(), Converter.Get());
	const FString SenderStr = Endpoint.ToString();
	AsyncTask(ENamedThreads::GameThread, [this, Message, SenderStr]()
	{
		DataReceivedDelegate.ExecuteIfBound(Message, SenderStr);
	});
}

FString FLUdpServer::GetLocalAddress() const
{
	return LocalEndpoint.ToString();
}
