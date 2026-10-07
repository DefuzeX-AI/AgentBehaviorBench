// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentActor.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "ue5project/Scene/Task/TaskStruct.h"
#include "ShipActor.generated.h"

/*



*/
UCLASS()
class UE5PROJECT_API AShipActor : public AEquipmentActor
{
	GENERATED_BODY()

public:
	AShipActor();


	void ExecuteEquipmentMoveTask2D(const FEquipmentMoveTask2D& InMoveTask2D);

	virtual void Tick(float DeltaTime) override;

protected:
	virtual void BeginPlay() override;


	virtual FSColor GetTagWidgetColor() const override;

	virtual FString GetImageSaveSubdir() const override;

	/**/
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Rescue")
	USphereComponent* SphereComp;

	/**/
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Mesh")
	UStaticMeshComponent* MeshComp;

	UFUNCTION()
	void OnSphereBeginOverlap(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	                          UPrimitiveComponent* OtherComp, int32 OtherBodyIndex,
	                          bool bFromSweep, const FHitResult& SweepResult);


	void OnRescuePeople(const ATaskPointActor* InTaskPointActor);

	/**/
	UPROPERTY(BlueprintReadOnly)
	TArray<FVector2D> MovePathPoints2D;
	double MoveSpeed2D = 0.0;
	int32 CurrentMoveTargetIndex2D = 1;
	bool bIsMoving2D = false;
	bool bRescuedThisMove2D = false;
	int64 TaskStartTime = 0;

	void UpdateHeadingToTarget(const FVector2D& InDirection2D);
	void SendRescueResult(bool bSucceed, const FString& InPersonId);
};
