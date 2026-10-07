#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskStruct.h"

class ATaskPointActor;
class AFireActor;
class ACongestionActor;
class ARescuePersonActor;
class APollutionActor;
class APipelineLeakActor;
class AWarehouseActor;
class ADeliveryActor;
class AQueueActor;

class UE5PROJECT_API FTaskMatrixController
{
public:
	static FTaskMatrixController* Get();

	// Fire
	void CreateFires(const TArray<FFirePositionInfo>& InFireInfos);
	AFireActor* CreateFire(const FFirePositionInfo& InFireInfo);
	void ClearFires();

	// Congestion
	void CreateCongestions(const TArray<FCongestionInfo>& InCongestionInfos);
	ACongestionActor* CreateCongestion(const FCongestionInfo& InCongestionInfo);
	void ClearCongestions();

	// RescuePerson
	void CreateRescuePersons(const TArray<FRescuePersonInfo>& InRescuePersonInfos);
	ARescuePersonActor* CreateRescuePerson(const FRescuePersonInfo& InRescuePersonInfo);
	void ClearRescuePersons();

	// Pollution
	void CreatePollutions(const TArray<FPollutionInfo>& InPollutionInfos);
	APollutionActor* CreatePollution(const FPollutionInfo& InPollutionInfo);
	void ClearPollutions();

	// PipelineLeak
	void CreatePipelineLeaks(const TArray<FPipelineLeakInfo>& InPipelineLeakInfos);
	APipelineLeakActor* CreatePipelineLeak(const FPipelineLeakInfo& InPipelineLeakInfo);
	void ClearPipelineLeaks();

	// Warehouse
	void CreateWarehouses(const TArray<FWarehouseInfo>& InWarehouseInfos);
	AWarehouseActor* CreateWarehouse(const FWarehouseInfo& InWarehouseInfo);
	void ClearWarehouses();

	// Delivery
	void CreateDeliveries(const TArray<FDeliveryInfo>& InDeliveryInfos);
	ADeliveryActor* CreateDelivery(const FDeliveryInfo& InDeliveryInfo);
	void ClearDeliveries();

	// Queuing
	void CreateQueues(const TArray<FQueuingInfo>& InQueuingInfos);
	AQueueActor* CreateQueue(const FQueuingInfo& InQueuingInfo);
	void ClearQueues();

	// All
	void ClearTaskPoints();
	ATaskPointActor* GetTaskPointActor(const FString& InTaskPointId) const;
	void RemoveTaskPoint(const FString& InTaskPointId);
protected:
	template<class T>
	void ClearTaskPointActor();
	template<class T>
	T* CreateTaskPointActor(const FString& InTaskPointId, const FVector& InPosition, const ETaskPointType InType);

	TMap<FString, TWeakObjectPtr<ATaskPointActor>> TaskPointMap;
};
