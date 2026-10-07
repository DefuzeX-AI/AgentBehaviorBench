// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "DataManager.generated.h"

/**
 * 
 */
UCLASS()
class UE5PROJECT_API ADataManager : public AActor
{
	GENERATED_BODY()
	
public:
	FString GetTaskId() const;
	
protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	
	// UDP
	void OnUdpReceiveMessage(const FString& InMessage, const FString& InSenderEndPoint);
	static void OnReceiveUdpDataMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveUdpEventMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveDroneMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveCarMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveDogMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveShipMessage(const TSharedPtr<FJsonObject>& InJsonObject);
	
	
	// WebSocket
	void OnWebSocketReceivedMessage(const FString& InMessage);
	void OnReceiveScenario(const TSharedPtr<FJsonObject>& InJsonObject);
	static void ParseScenarioEquipments(const TSharedPtr<FJsonObject>& InJsonObject);
	static void ParseScenarioTaskMatrix(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveTakePhotoTask(const TSharedPtr<FJsonObject>& InJsonObject);
	static void OnReceiveEquipmentMoveTask2D(const TSharedPtr<FJsonObject>& InJsonObject);
	void ResetScene();
	
	void OnWebSocketConnectionError(const FString& InError);
	void OnWebSocketClosed(const int32 InStatusCode, const FString& InReason, const bool bWasClean);


	static void WebSocketSendMessage(const FString& InMessage);
public:
	void SendShipRescueMessage(const FString& InShipId, const int32 InDuringSeconds, const bool bSucceed, 
		const FString& InPersonId, const FVector& InShipLocation) const;
	
	
protected:
	FString TaskId;
	
	
	friend class UBlueprintTempHelper;
};




