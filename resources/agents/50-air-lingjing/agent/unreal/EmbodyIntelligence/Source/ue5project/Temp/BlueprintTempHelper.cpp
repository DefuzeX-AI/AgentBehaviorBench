// Fill out your copyright notice in the Description page of Project Settings.


#include "BlueprintTempHelper.h"

#include "Kismet/GameplayStatics.h"
#include "ue5project/Core/DataManager.h"
#include "ue5project/Core/GamePlayManager.h"
#include "ue5project/Scene/Equipment/FEquipmentController.h"
#include "ue5project/Scene/Task/TaskMatrixController.h"

void UBlueprintTempHelper::SetWorld(AActor* WordContext)
{
	if (WordContext && WordContext->IsValidLowLevel())
	{
		FGamePlayManager::Get()->WorldContext = WordContext->GetWorld();
	}
}

void UBlueprintTempHelper::ReceiveWebSocketMessage(AActor* WorldContext, const FString InMessage)
{
	if (WorldContext && WorldContext->IsValidLowLevel())
	{
		AActor* Actor = UGameplayStatics::GetActorOfClass(WorldContext, ADataManager::StaticClass());
		if (ADataManager* DataManager = Cast<ADataManager>(Actor))
		{
			DataManager->OnWebSocketReceivedMessage(InMessage);
		}
	}
}

void UBlueprintTempHelper::ReceiveUdpMessage(AActor* WorldContext, const FString InMessage)
{
	if (WorldContext && WorldContext->IsValidLowLevel())
	{
		AActor* Actor = UGameplayStatics::GetActorOfClass(WorldContext, ADataManager::StaticClass());
		if (ADataManager* DataManager = Cast<ADataManager>(Actor))
		{
			DataManager->OnUdpReceiveMessage(InMessage, TEXT(""));
		}
	}
}

void UBlueprintTempHelper::TestQueueActor()
{
	FQueuingInfo QueuingInfo;
	FTaskMatrixController::Get()->CreateQueue(QueuingInfo);
}

AEquipmentActor* UBlueprintTempHelper::GetEquipment(const FString& InEquipmentId)
{
	return FEquipmentController::Get()->GetEquipment(InEquipmentId);
}

TArray<AEquipmentActor*> UBlueprintTempHelper::GetEquipments()
{
	return FEquipmentController::Get()->GetEquipments();
}

void UBlueprintTempHelper::RegisterDataManager(ADataManager* InDataManager)
{
	FTempController::Get()->DataManager = InDataManager;
}
