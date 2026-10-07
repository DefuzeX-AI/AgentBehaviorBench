// Fill out your copyright notice in the Description page of Project Settings.

#include "LUdpClient.h"
#include "SocketSubsystem.h"
#include "Common/UdpSocketBuilder.h"

FLUdpClient::~FLUdpClient()
{
	Stop();
}

FLUdpClient* FLUdpClient::Get()
{
	static FLUdpClient Instance;
	return &Instance;
}

bool FLUdpClient::Start(const FString& InSocketName, int32 InLocalPort, const FString& InRemoteIP, int32 InRemotePort)
{
	if (bIsRunning)
	{
		return true;
	}

	// Parse remote endpoint
	FIPv4Address RemoteAddr;
	if (!FIPv4Address::Parse(InRemoteIP, RemoteAddr))
	{
		UE_LOG(LogTemp, Error, TEXT("LUdpClient: Invalid remote IP %s"), *InRemoteIP);
		return false;
	}
	RemoteEndpoint = FIPv4Endpoint(RemoteAddr, InRemotePort);

	// Create and bind UDP socket
	ISocketSubsystem* SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SocketSubsystem)
	{
		UE_LOG(LogTemp, Error, TEXT("LUdpClient: Failed to get socket subsystem"));
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
		UE_LOG(LogTemp, Error, TEXT("LUdpClient: Failed to create socket on port %d"), InLocalPort);
		return false;
	}

	// Resolve local endpoint
	const TSharedRef<FInternetAddr> LocalAddr = SocketSubsystem->GetLocalBindAddr(*GLog);
	const int32 BoundPort = UdpSocket->GetPortNo();
	LocalAddr->SetPort(BoundPort);
	LocalEndpoint = FIPv4Endpoint(LocalAddr);

	// Start receiver
	SocketReceiver = MakeShared<FUdpSocketReceiver>(UdpSocket, FTimespan::FromMilliseconds(100), *InSocketName);
	SocketReceiver->OnDataReceived().BindRaw(this, &FLUdpClient::HandleDataReceived);
	SocketReceiver->Start();

	bIsRunning = true;
	UE_LOG(LogTemp, Log, TEXT("LUdpClient: Started on %s, remote %s"), *LocalEndpoint.ToString(), *RemoteEndpoint.ToString());
	return true;
}

void FLUdpClient::Stop()
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
	UE_LOG(LogTemp, Log, TEXT("LUdpClient: Stopped"));
}

bool FLUdpClient::Send(const TArray<uint8>& Data) const
{
	if (!bIsRunning || !UdpSocket || Data.Num() == 0)
	{
		return false;
	}

	int32 BytesSent = 0;
	return UdpSocket->SendTo(Data.GetData(), Data.Num(), BytesSent, *RemoteEndpoint.ToInternetAddr());
}

bool FLUdpClient::Send(const FString& Message) const
{
	const FTCHARToUTF8 Convert(*Message);
	const TArray Data(reinterpret_cast<const uint8*>(Convert.Get()), Convert.Length());
	return Send(Data);
}

bool FLUdpClient::SendTo(const TArray<uint8>& Data, const FString& RemoteIP, int32 RemotePort) const
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

void FLUdpClient::HandleDataReceived(const FArrayReaderPtr& Data, const FIPv4Endpoint& Endpoint) const
{
	const FString Message(reinterpret_cast<const ANSICHAR*>(Data->GetData()), Data->TotalSize());
	const FString SenderStr = Endpoint.ToString();
	AsyncTask(ENamedThreads::GameThread, [this, Message, SenderStr]()
	{
		DataReceivedDelegate.ExecuteIfBound(Message, SenderStr);
	});
}

FString FLUdpClient::GetLocalAddress() const
{
	return LocalEndpoint.ToString();
}

FString FLUdpClient::GetRemoteAddress() const
{
	return RemoteEndpoint.ToString();
}
