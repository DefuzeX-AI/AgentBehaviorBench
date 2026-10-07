// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BlueprintTempHelper.generated.h"

class ADataManager;
class AEquipmentActor;
/**
 * 
 */
UCLASS()
class UE5PROJECT_API UBlueprintTempHelper : public UObject
{
	GENERATED_BODY()
	
public:
	UFUNCTION(BlueprintCallable)
	static void SetWorld(AActor* WordContext);
	UFUNCTION(BlueprintCallable)
	static void ReceiveWebSocketMessage(AActor* WorldContext, const FString InMessage);
	UFUNCTION(BlueprintCallable)
	static void ReceiveUdpMessage(AActor* WorldContext, const FString InMessage);
	
	UFUNCTION(BlueprintCallable)
	static void TestQueueActor();
	
	UFUNCTION(BlueprintCallable)
	static AEquipmentActor* GetEquipment(const FString& InEquipmentId);
	UFUNCTION(BlueprintCallable)
	static TArray<AEquipmentActor*> GetEquipments();
	UFUNCTION(BlueprintCallable)
	static void RegisterDataManager(ADataManager* InDataManager);
	
};





class UE5PROJECT_API FTempController
{
public:
	static FTempController* Get()
	{
		static FTempController Instance;
		return &Instance;
	}
	
	TWeakObjectPtr<ADataManager> DataManager;
	
	
};