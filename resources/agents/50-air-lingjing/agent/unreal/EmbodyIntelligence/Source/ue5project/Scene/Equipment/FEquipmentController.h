// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentStruct.h"
#include "ue5project/Net/MessageHelper/PhotoRequest/LPhotoRequestStruct.h"

class AEquipmentActor;
class UClass;

class UE5PROJECT_API FEquipmentController
{
public:
	static FEquipmentController* Get();

	void CreateDrones(const TArray<FDroneInfo>& InDroneInfos);
	void CreateDrone(const FDroneInfo& InDroneInfo);
	void CreateCars(const TArray<FCarInfo>& InCarInfos);
	void CreateCar(const FCarInfo& InCarInfo);
	void CreateDogs(const TArray<FDogInfo>& InDogInfos);
	void CreateDog(const FDogInfo& InDogInfo);
	void CreateShips(const TArray<FShipInfo>& InShipInfos);
	void CreateShip(const FShipInfo& InShipInfo);
	AEquipmentActor* GetEquipment(const FString& InEquipmentId) const;
	TArray<AEquipmentActor*> GetEquipments() const;
	void RemoveEquipments(const TArray<FString>& InEquipmentIds);
	void RemoveEquipment(const FString& InEquipmentId);
	
	void ClearEquipments();

private:
	TMap<FString, TWeakObjectPtr<AEquipmentActor>> EquipmentMap;

	AEquipmentActor* SpawnEquipment(const FString& InId, const FString& InName, const EEquipmentType InType,
		const FVector& InLocation, const FSoftObjectPath& InBlueprintPath);

	AEquipmentActor* SpawnEquipmentByClass(const FString& InId, const FString& InName, const EEquipmentType InType,
		const FVector& InLocation, UClass* InClass);
	
public:
	void ExecuteTakePhotoTasks(const TArray<FPhotoTaskInfo>& InTaskInfos) const;
	
	
	
};
