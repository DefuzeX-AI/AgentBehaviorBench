// Fill out your copyright notice in the Description page of Project Settings.

#include "FEquipmentController.h"
#include "EquipmentActor.h"
#include "ShipActor.h"
#include "Engine/World.h"
#include "ue5project/Core/GamePlayManager.h"

FEquipmentController* FEquipmentController::Get()
{
	static FEquipmentController Instance;
	return &Instance;
}

void FEquipmentController::CreateDrones(const TArray<FDroneInfo>& InDroneInfos)
{
	for (const FDroneInfo& DroneInfo : InDroneInfos)
	{
		CreateDrone(DroneInfo);
	}
}

void FEquipmentController::CreateDrone(const FDroneInfo& InDroneInfo)
{
	static const FSoftObjectPath DroneBlueprintPath(TEXT("/Script/Engine.Blueprint'/EmbodyIntelligence/Program/Equipment/BP_Drone.BP_Drone_C'"));
	SpawnEquipment(InDroneInfo.Id, InDroneInfo.Name, EEquipmentType::Drone, InDroneInfo.Location, DroneBlueprintPath);
}

void FEquipmentController::CreateCars(const TArray<FCarInfo>& InCarInfos)
{
	for (const FCarInfo& CarInfo : InCarInfos)
	{
		CreateCar(CarInfo);
	}
}

void FEquipmentController::CreateCar(const FCarInfo& InCarInfo)
{
	static const FSoftObjectPath CarBlueprintPath(TEXT("/Script/Engine.Blueprint'/EmbodyIntelligence/Program/Equipment/BP_Car.BP_Car_C'"));
	SpawnEquipment(InCarInfo.Id, InCarInfo.Name, EEquipmentType::Car, InCarInfo.Location, CarBlueprintPath);
}

void FEquipmentController::CreateDogs(const TArray<FDogInfo>& InDogInfos)
{
	for (const FDogInfo& DogInfo : InDogInfos)
	{
		CreateDog(DogInfo);
	}
}

void FEquipmentController::CreateDog(const FDogInfo& InDogInfo)
{
	static const FSoftObjectPath DogBlueprintPath(TEXT("/Script/Engine.Blueprint'/EmbodyIntelligence/Program/Equipment/BP_Dog.BP_Dog_C'"));
	if (AEquipmentActor* DogActor = SpawnEquipment(InDogInfo.Id, InDogInfo.Name, EEquipmentType::Dog, InDogInfo.Location, DogBlueprintPath))
	{
		DogActor->SetEquipmentScale(FVector(InDogInfo.Scale));
	}
}

void FEquipmentController::CreateShips(const TArray<FShipInfo>& InShipInfos)
{
	for (const FShipInfo& ShipInfo : InShipInfos)
	{
		CreateShip(ShipInfo);
	}
}

void FEquipmentController::CreateShip(const FShipInfo& InShipInfo)
{

	AEquipmentActor* Spawned = SpawnEquipmentByClass(
		InShipInfo.Id, InShipInfo.Name, EEquipmentType::Ship, InShipInfo.Location, AShipActor::StaticClass());
	if (AShipActor* ShipActor = Cast<AShipActor>(Spawned))
	{
		ShipActor->SetActorRotation(FRotator(0.0, InShipInfo.Heading, 0.0));
	}
}

AEquipmentActor* FEquipmentController::GetEquipment(const FString& InEquipmentId) const
{
	return EquipmentMap.FindRef(InEquipmentId).Get();
}

TArray<AEquipmentActor*> FEquipmentController::GetEquipments() const
{
	TArray<AEquipmentActor*> Equipments;
	for (const TPair<FString, TWeakObjectPtr<AEquipmentActor>>& Pair : EquipmentMap)
	{
		if (AEquipmentActor* EquipmentActor = Pair.Value.Get())
		{
			Equipments.Add(EquipmentActor);
		}
	}
	return Equipments;
}

void FEquipmentController::RemoveEquipments(const TArray<FString>& InEquipmentIds)
{
	for (const FString& EquipmentId : InEquipmentIds)
	{
		RemoveEquipment(EquipmentId);
	}
}

void FEquipmentController::RemoveEquipment(const FString& InEquipmentId)
{
	if (AEquipmentActor* Equipment = EquipmentMap.FindRef(InEquipmentId).Get())
	{
		Equipment->Destroy();
	}
	EquipmentMap.Remove(InEquipmentId);
}

void FEquipmentController::ClearEquipments()
{
	for (const TPair<FString, TWeakObjectPtr<AEquipmentActor>>& Pair : EquipmentMap)
	{
		if (AEquipmentActor* EquipmentActor = Pair.Value.Get())
		{
			EquipmentActor->Destroy();
		}
	}
	EquipmentMap.Empty();
}

AEquipmentActor* FEquipmentController::SpawnEquipment(const FString& InId, const FString& InName,
                                                      const EEquipmentType InType, const FVector& InLocation, const FSoftObjectPath& InBlueprintPath)
{
	UClass* BlueprintClass = LoadClass<AEquipmentActor>(nullptr, *InBlueprintPath.ToString());
	if (!BlueprintClass)
	{
		UE_LOG(LogTemp, Error, TEXT("FEquipmentController: Failed to load blueprint: %s"), *InBlueprintPath.ToString());
		return nullptr;
	}
	return SpawnEquipmentByClass(InId, InName, InType, InLocation, BlueprintClass);
}

AEquipmentActor* FEquipmentController::SpawnEquipmentByClass(const FString& InId, const FString& InName,
	const EEquipmentType InType, const FVector& InLocation, UClass* InClass)
{
	if (!InClass)
	{
		UE_LOG(LogTemp, Error, TEXT("FEquipmentController: Null class for %s"), *InId);
		return nullptr;
	}

	if (EquipmentMap.Find(InId))
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
			FString::Printf(TEXT("FEquipmentController: Duplicate EquipmentId: %s"), *InId));
		return nullptr;
	}

	UWorld* World = FGamePlayManager::Get()->WorldContext.Get();
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("FEquipmentController: No valid world to spawn equipment"));
		return nullptr;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AEquipmentActor* EquipmentActor = World->SpawnActor<AEquipmentActor>(InClass, InLocation, FRotator::ZeroRotator, SpawnParams);
	if (!EquipmentActor)
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Red,
			FString::Printf(TEXT("FEquipmentController: Spawn %s Failed"), *InId));
		return nullptr;
	}
	FEquipmentInfo EquipmentInfo;
	EquipmentInfo.EquipmentId = InId;
	EquipmentInfo.EquipmentName = InName;
	EquipmentInfo.Type = InType;
	EquipmentActor->InitEquipment(EquipmentInfo);
	EquipmentMap.Add(InId, EquipmentActor);
	return EquipmentActor;
}

void FEquipmentController::ExecuteTakePhotoTasks(const TArray<FPhotoTaskInfo>& InTaskInfos) const
{
	for (const FPhotoTaskInfo& TaskInfo : InTaskInfos)
	{
		if (AEquipmentActor* EquipmentActor = EquipmentMap.FindRef(TaskInfo.EquipmentId).Get())
		{
			EquipmentActor->ExecuteTakePhotoTask(TaskInfo);
		}
	}
}
