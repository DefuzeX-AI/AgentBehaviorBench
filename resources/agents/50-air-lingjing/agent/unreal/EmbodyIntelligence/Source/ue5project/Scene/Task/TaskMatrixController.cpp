#include "TaskMatrixController.h"
#include "Fire/FireActor.h"
#include "Congestion/CongestionActor.h"
#include "Rescue/RescuePersonActor.h"
#include "Pipeline/PipelineLeakActor.h"
#include "Pollution/PollutionActor.h"
#include "Warehouse/WarehouseActor.h"
#include "Warehouse/DeliveryActor.h"
#include "Queuing/QueueActor.h"
#include "ue5project/Core/GamePlayManager.h"

FTaskMatrixController* FTaskMatrixController::Get()
{
	static FTaskMatrixController Instance;
	return &Instance;
}

// === Fire ===

void FTaskMatrixController::CreateFires(const TArray<FFirePositionInfo>& InFireInfos)
{
	for (const FFirePositionInfo& FireInfo : InFireInfos)
	{
		if (const AFireActor* FireActor = CreateFire(FireInfo))
		{
			FireActor->SetFireScale(FVector(FireInfo.Scale));
		}
	}
}

AFireActor* FTaskMatrixController::CreateFire(const FFirePositionInfo& InFireInfo)
{
	return CreateTaskPointActor<AFireActor>(InFireInfo.FireId, InFireInfo.Position, ETaskPointType::GoalFire);
}

void FTaskMatrixController::ClearFires()
{
	ClearTaskPointActor<AFireActor>();
}

// === Congestion ===

void FTaskMatrixController::CreateCongestions(const TArray<FCongestionInfo>& InCongestionInfos)
{
	for (const FCongestionInfo& Info : InCongestionInfos)
	{
		if (ACongestionActor* CongestionActor = CreateCongestion(Info))
		{
			FRotator&& Rotation = CongestionActor->GetActorRotation();
			Rotation.Yaw = Info.Yaw;
			CongestionActor->SetActorRotation(Rotation);
		}
	}
}

ACongestionActor* FTaskMatrixController::CreateCongestion(const FCongestionInfo& InCongestionInfo)
{
	return CreateTaskPointActor<ACongestionActor>(InCongestionInfo.ConId, InCongestionInfo.Position, ETaskPointType::Congestion);
}

void FTaskMatrixController::ClearCongestions()
{
	ClearTaskPointActor<ACongestionActor>();
}

// === RescuePerson ===

void FTaskMatrixController::CreateRescuePersons(const TArray<FRescuePersonInfo>& InRescuePersonInfos)
{
	for (const FRescuePersonInfo& Info : InRescuePersonInfos)
	{
		CreateRescuePerson(Info);
	}
}

ARescuePersonActor* FTaskMatrixController::CreateRescuePerson(const FRescuePersonInfo& InRescuePersonInfo)
{
	return CreateTaskPointActor<ARescuePersonActor>(InRescuePersonInfo.PersonId, InRescuePersonInfo.Position, ETaskPointType::RescuePerson);
}

void FTaskMatrixController::ClearRescuePersons()
{
	ClearTaskPointActor<ARescuePersonActor>();
}

// === Pollution ===

void FTaskMatrixController::CreatePollutions(const TArray<FPollutionInfo>& InPollutionInfos)
{
	for (const FPollutionInfo& Info : InPollutionInfos)
	{
		CreatePollution(Info);
	}
}

APollutionActor* FTaskMatrixController::CreatePollution(const FPollutionInfo& InPollutionInfo)
{
	return CreateTaskPointActor<APollutionActor>(InPollutionInfo.PollutionId, InPollutionInfo.Position, ETaskPointType::Pollution);
}

void FTaskMatrixController::ClearPollutions()
{
	ClearTaskPointActor<APollutionActor>();
}

// === PipelineLeak ===

void FTaskMatrixController::CreatePipelineLeaks(const TArray<FPipelineLeakInfo>& InPipelineLeakInfos)
{
	for (const FPipelineLeakInfo& Info : InPipelineLeakInfos)
	{
		CreatePipelineLeak(Info);
	}
}

APipelineLeakActor* FTaskMatrixController::CreatePipelineLeak(const FPipelineLeakInfo& InPipelineLeakInfo)
{
	return CreateTaskPointActor<APipelineLeakActor>(InPipelineLeakInfo.PipeId, InPipelineLeakInfo.Position, ETaskPointType::PipeLineLeak);
}

void FTaskMatrixController::ClearPipelineLeaks()
{
	ClearTaskPointActor<APipelineLeakActor>();
}

// === Warehouse ===

void FTaskMatrixController::CreateWarehouses(const TArray<FWarehouseInfo>& InWarehouseInfos)
{
	for (const FWarehouseInfo& Info : InWarehouseInfos)
	{
		CreateWarehouse(Info);
	}
}

AWarehouseActor* FTaskMatrixController::CreateWarehouse(const FWarehouseInfo& InWarehouseInfo)
{
	return CreateTaskPointActor<AWarehouseActor>(InWarehouseInfo.WarehouseId, InWarehouseInfo.Position, ETaskPointType::Warehouse);
}

void FTaskMatrixController::ClearWarehouses()
{
	ClearTaskPointActor<AWarehouseActor>();
}

// === Delivery ===

void FTaskMatrixController::CreateDeliveries(const TArray<FDeliveryInfo>& InDeliveryInfos)
{
	for (const FDeliveryInfo& Info : InDeliveryInfos)
	{
		CreateDelivery(Info);
	}
}

ADeliveryActor* FTaskMatrixController::CreateDelivery(const FDeliveryInfo& InDeliveryInfo)
{
	return CreateTaskPointActor<ADeliveryActor>(InDeliveryInfo.DelId, InDeliveryInfo.Position, ETaskPointType::Delivery);
}

void FTaskMatrixController::ClearDeliveries()
{
	ClearTaskPointActor<ADeliveryActor>();
}

// === Queuing ===

void FTaskMatrixController::CreateQueues(const TArray<FQueuingInfo>& InQueuingInfos)
{
	for (const FQueuingInfo& Info : InQueuingInfos)
	{
		CreateQueue(Info);
	}
}

AQueueActor* FTaskMatrixController::CreateQueue(const FQueuingInfo& InQueuingInfo)
{
	if (TaskPointMap.Find(InQueuingInfo.QueueId))
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
			FString::Printf(TEXT("FTaskMatrixController: Duplicate QueueId: %s"), *InQueuingInfo.QueueId));
		return nullptr;
	}

	AQueueActor* QueueActor = CreateTaskPointActor<AQueueActor>(InQueuingInfo.QueueId, InQueuingInfo.Location, ETaskPointType::Queuing);
	if (QueueActor)
	{
		QueueActor->SetActorRotation(FRotator(0.0, InQueuingInfo.Heading, 0.0));
		QueueActor->InitQueue(InQueuingInfo);
	}
	return QueueActor;
}

void FTaskMatrixController::ClearQueues()
{
	ClearTaskPointActor<AQueueActor>();
}

// === All ===

void FTaskMatrixController::ClearTaskPoints()
{
	for (const TPair<FString, TWeakObjectPtr<ATaskPointActor>>& Pair : TaskPointMap)
	{
		if (ATaskPointActor* Actor = Pair.Value.Get())
		{
			Actor->Destroy();
		}
	}
	TaskPointMap.Empty();
}

ATaskPointActor* FTaskMatrixController::GetTaskPointActor(const FString& InTaskPointId) const
{
	return TaskPointMap.FindRef(InTaskPointId).Get();
}

void FTaskMatrixController::RemoveTaskPoint(const FString& InTaskPointId)
{
	if (ATaskPointActor* Actor = TaskPointMap.FindRef(InTaskPointId).Get())
	{
		Actor->Destroy();
	}
	TaskPointMap.Remove(InTaskPointId);
}

template <class T>
void FTaskMatrixController::ClearTaskPointActor()
{
	TArray<FString> Ids;
	for (const TPair<FString, TWeakObjectPtr<ATaskPointActor>>& Pair : TaskPointMap)
	{
		if (T* TaskPointActor = Cast<T>(Pair.Value))
		{
			Ids.Add(Pair.Key);
			TaskPointActor->Destroy();
		}
	}
	for (const FString& Id : Ids)
	{
		TaskPointMap.Remove(Id);
	}
}

template <class T>
T* FTaskMatrixController::CreateTaskPointActor(const FString& InTaskPointId, const FVector& InPosition, const ETaskPointType InType)
{
	if (UWorld* World = FGamePlayManager::Get()->WorldContext.Get())
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		if (T* TaskPointActor = World->SpawnActor<T>(InPosition, FRotator::ZeroRotator, SpawnParams))
		{
			FTaskPointInfo TaskPointInfo;
			TaskPointInfo.TaskPointId = InTaskPointId;
			TaskPointInfo.TaskPointType = InType;
			TaskPointActor->InitTaskPoint(TaskPointInfo);
			TaskPointMap.Add(InTaskPointId, TaskPointActor);
			return TaskPointActor;
		}
	}
	return nullptr;
}
